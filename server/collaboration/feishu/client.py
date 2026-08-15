from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx

from server.utils.custom_logger import get_logger

logger = get_logger(__name__)

FEISHU_OPENAPI_BASE = "https://open.feishu.cn/open-apis"
MAX_SAFE_ERROR_LENGTH = 500


def safe_feishu_error_message(
    error: object,
    *,
    max_length: int = MAX_SAFE_ERROR_LENGTH,
    secrets: list[str | None] | None = None,
) -> str:
    message = str(error) or error.__class__.__name__
    credential_key = r"(?:app[_-]?secret|appSecret|tenant[_-]?access[_-]?token|tenantAccessToken|authorization)"
    redacted = re.sub(r"(?i)Bearer\s+[A-Za-z0-9._~+/=-]+", "Bearer [redacted]", message)
    redacted = re.sub(
        rf'(?i)["\']?{credential_key}["\']?\s*[:=]\s*(["\'])[^"\']+(\1)',
        "[redacted]",
        redacted,
    )
    redacted = re.sub(
        rf"(?i)[\"']?{credential_key}[\"']?\s*[:=]\s*[^,\s;}}]+",
        "[redacted]",
        redacted,
    )
    for secret in secrets or []:
        if secret:
            redacted = redacted.replace(secret, "[redacted]")
    if len(redacted) > max_length:
        redacted = redacted[: max_length - 3] + "..."
    return redacted


@dataclass(slots=True)
class TenantAccessToken:
    value: str
    expires_at: float

    def is_valid(self, skew_seconds: int = 120) -> bool:
        return bool(self.value) and time.time() < self.expires_at - skew_seconds


class FeishuTokenCache:
    """Process-local tenant token cache. Tenant access tokens are intentionally not persisted."""

    def __init__(self) -> None:
        self._cache: dict[str, TenantAccessToken] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def _key(self, app_id: str) -> str:
        return app_id

    def get(self, app_id: str) -> str | None:
        token = self._cache.get(self._key(app_id))
        if token and token.is_valid():
            return token.value
        return None

    def expires_at(self, app_id: str) -> float | None:
        token = self._cache.get(self._key(app_id))
        if not token:
            return None
        return token.expires_at

    def set(self, app_id: str, token: str, expire_seconds: int) -> None:
        self._cache[self._key(app_id)] = TenantAccessToken(
            value=token,
            expires_at=time.time() + max(expire_seconds, 0),
        )

    def clear(self, app_id: str | None = None) -> None:
        if app_id is None:
            self._cache.clear()
        else:
            self._cache.pop(self._key(app_id), None)

    def lock_for(self, app_id: str) -> asyncio.Lock:
        key = self._key(app_id)
        lock = self._locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[key] = lock
        return lock


token_cache = FeishuTokenCache()


class FeishuApiError(Exception):
    def __init__(self, message: str, code: int | None = None) -> None:
        super().__init__(message)
        self.code = code


REAUTH_ERROR_CODES = {
    99991663,  # invalid tenant access token / app credential class
    99991664,
    99991668,
    99991669,
    99991672,
}


def feishu_error_requires_reauth(error: object) -> bool:
    code = getattr(error, "code", None)
    if isinstance(code, int) and code in REAUTH_ERROR_CODES:
        return True
    message = str(error).lower()
    markers = (
        "invalid app_secret",
        "invalid app secret",
        "invalid tenant_access_token",
        "invalid tenant access token",
        "tenant_access_token invalid",
        "app not installed",
        "app_ticket",
        "access token is invalid",
        "invalid_access_token",
        "unauthorized",
    )
    return any(marker in message for marker in markers)


class FeishuApiClient:
    def __init__(
        self,
        app_id: str,
        app_secret: str,
        *,
        base_url: str = FEISHU_OPENAPI_BASE,
        http_client: httpx.AsyncClient | None = None,
        cache: FeishuTokenCache = token_cache,
    ) -> None:
        self.app_id = app_id
        self.app_secret = app_secret
        self.base_url = base_url.rstrip("/")
        self._http_client = http_client
        self._cache = cache

    async def tenant_access_token(self) -> str:
        cache_key = self._token_cache_key()
        cached = self._cache.get(cache_key)
        if cached:
            return cached

        async with self._cache.lock_for(cache_key):
            cached = self._cache.get(cache_key)
            if cached:
                return cached
            return await self._fetch_and_cache_tenant_access_token(cache_key)

    async def _tenant_access_token_after_reauth_failure(self, rejected_token: str) -> str:
        cache_key = self._token_cache_key()
        async with self._cache.lock_for(cache_key):
            cached = self._cache.get(cache_key)
            if cached and cached != rejected_token:
                return cached
            self._cache.clear(cache_key)
            return await self._fetch_and_cache_tenant_access_token(cache_key)

    async def _fetch_and_cache_tenant_access_token(self, cache_key: str) -> str:
        payload = {"app_id": self.app_id, "app_secret": self.app_secret}
        data = await self._post_json_without_auth("/auth/v3/tenant_access_token/internal", payload)
        token = data.get("tenant_access_token")
        if not token:
            raise FeishuApiError("Feishu tenant token response did not include tenant_access_token")
        self._cache.set(cache_key, token, int(data.get("expire", 7200)))
        return token

    def _token_cache_key(self) -> str:
        secret_fingerprint = hashlib.sha256(self.app_secret.encode("utf-8")).hexdigest()[:16]
        return f"{self.app_id}:{secret_fingerprint}"

    async def probe(self) -> dict[str, Any]:
        response = await self._authenticated_request("GET", "/bot/v3/info")
        bot = response.get("bot", response)
        token_expires_at = self._cache.expires_at(self._token_cache_key())
        return {
            "ok": True,
            "bot": bot,
            "bot_external_id": bot.get("open_id") or bot.get("app_name") or bot.get("name"),
            "external_tenant_id": bot.get("tenant_key") or bot.get("app_id") or self.app_id,
            "external_tenant_name": bot.get("tenant_name") or bot.get("app_name") or "Feishu tenant",
            "tenant_token_expires_at": datetime.fromtimestamp(token_expires_at).isoformat() if token_expires_at else None,
        }

    async def list_chats(self, *, page_size: int = 50, max_items: int = 200) -> list[dict[str, Any]]:
        chats: list[dict[str, Any]] = []
        page_token: str | None = None
        safe_page_size = max(1, min(page_size, 100))
        while len(chats) < max_items:
            path = f"/im/v1/chats?page_size={safe_page_size}"
            if page_token:
                path += f"&page_token={page_token}"
            data = await self._authenticated_request("GET", path)
            for item in data.get("items", []):
                chat_id = item.get("chat_id")
                if not chat_id:
                    continue
                chats.append(
                    {
                        "chat_id": chat_id,
                        "name": item.get("name") or item.get("description") or chat_id,
                        "chat_type": item.get("chat_type"),
                        "avatar": item.get("avatar"),
                    }
                )
                if len(chats) >= max_items:
                    break
            if not data.get("has_more") or not data.get("page_token"):
                break
            page_token = data.get("page_token")
        return chats

    async def send_text_message(
        self,
        *,
        receive_id_type: str,
        receive_id: str,
        text: str,
        root_id: str | None = None,
        request_uuid: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "receive_id": receive_id,
            "msg_type": "text",
            "content": json.dumps({"text": text}, ensure_ascii=False),
        }
        if root_id:
            payload["root_id"] = root_id
        if request_uuid:
            payload["uuid"] = request_uuid
        return await self._authenticated_request(
            "POST",
            f"/im/v1/messages?receive_id_type={receive_id_type}",
            json=payload,
        )

    async def reply_text_message(self, *, message_id: str, text: str, request_uuid: str | None = None) -> dict[str, Any]:
        payload = {"msg_type": "text", "content": json.dumps({"text": text}, ensure_ascii=False)}
        if request_uuid:
            payload["uuid"] = request_uuid
        return await self._authenticated_request("POST", f"/im/v1/messages/{message_id}/reply", json=payload)

    async def _post_json_without_auth(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        async with self._client() as client:
            response = await client.post(f"{self.base_url}{path}", json=payload)
        return self._decode_response(response)

    async def _request(self, method: str, path: str, *, token: str, json: dict[str, Any] | None = None) -> dict[str, Any]:
        response: httpx.Response | None = None
        for attempt in range(3):
            async with self._client() as client:
                response = await client.request(
                    method,
                    f"{self.base_url}{path}",
                    headers={"Authorization": f"Bearer {token}"},
                    json=json,
                )
            if response.status_code != 429 or attempt == 2:
                break
            retry_after = response.headers.get("Retry-After")
            try:
                delay = min(float(retry_after), 2.0) if retry_after else 0.5 * (attempt + 1)
            except ValueError:
                delay = 0.5 * (attempt + 1)
            await asyncio.sleep(delay)
        assert response is not None
        return self._decode_response(response)

    async def _authenticated_request(self, method: str, path: str, *, json: dict[str, Any] | None = None) -> dict[str, Any]:
        token = await self.tenant_access_token()
        try:
            return await self._request(method, path, token=token, json=json)
        except FeishuApiError as exc:
            if not feishu_error_requires_reauth(exc):
                raise
            refreshed_token = await self._tenant_access_token_after_reauth_failure(token)
            return await self._request(method, path, token=refreshed_token, json=json)

    def _client(self):
        if self._http_client is not None:
            return _BorrowedAsyncClient(self._http_client)
        return httpx.AsyncClient(timeout=20.0)

    @staticmethod
    def _decode_response(response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except Exception:
            response.raise_for_status()
            raise FeishuApiError("Feishu response was not JSON")

        code = payload.get("code", 0)
        if response.status_code >= 400 or code not in (0, None):
            msg = payload.get("msg") or payload.get("message") or f"HTTP {response.status_code}"
            raise FeishuApiError(safe_feishu_error_message(msg), code=code if isinstance(code, int) else None)
        data = payload.get("data")
        return data if isinstance(data, dict) else payload


class _BorrowedAsyncClient:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def __aenter__(self) -> httpx.AsyncClient:
        return self._client

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

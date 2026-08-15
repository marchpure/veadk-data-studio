from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any

import httpx

from server.utils.custom_logger import get_logger

logger = get_logger(__name__)

FEISHU_OPENAPI_BASE = "https://open.feishu.cn/open-apis"


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

    def _key(self, app_id: str) -> str:
        return app_id

    def get(self, app_id: str) -> str | None:
        token = self._cache.get(self._key(app_id))
        if token and token.is_valid():
            return token.value
        return None

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


token_cache = FeishuTokenCache()


class FeishuApiError(Exception):
    def __init__(self, message: str, code: int | None = None) -> None:
        super().__init__(message)
        self.code = code


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
        token = await self.tenant_access_token()
        response = await self._request("GET", "/bot/v3/info", token=token)
        bot = response.get("bot", response)
        return {
            "ok": True,
            "bot": bot,
            "bot_external_id": bot.get("open_id") or bot.get("app_name") or bot.get("name"),
            "external_tenant_id": bot.get("tenant_key") or bot.get("app_id") or self.app_id,
            "external_tenant_name": bot.get("tenant_name") or bot.get("app_name") or "Feishu tenant",
        }

    async def send_text_message(
        self,
        *,
        receive_id_type: str,
        receive_id: str,
        text: str,
        root_id: str | None = None,
    ) -> dict[str, Any]:
        token = await self.tenant_access_token()
        payload: dict[str, Any] = {
            "receive_id": receive_id,
            "msg_type": "text",
            "content": json.dumps({"text": text}, ensure_ascii=False),
        }
        if root_id:
            payload["root_id"] = root_id
        return await self._request(
            "POST",
            f"/im/v1/messages?receive_id_type={receive_id_type}",
            token=token,
            json=payload,
        )

    async def reply_text_message(self, *, message_id: str, text: str) -> dict[str, Any]:
        token = await self.tenant_access_token()
        payload = {"msg_type": "text", "content": json.dumps({"text": text}, ensure_ascii=False)}
        return await self._request("POST", f"/im/v1/messages/{message_id}/reply", token=token, json=payload)

    async def _post_json_without_auth(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        async with self._client() as client:
            response = await client.post(f"{self.base_url}{path}", json=payload)
        return self._decode_response(response)

    async def _request(self, method: str, path: str, *, token: str, json: dict[str, Any] | None = None) -> dict[str, Any]:
        async with self._client() as client:
            response = await client.request(
                method,
                f"{self.base_url}{path}",
                headers={"Authorization": f"Bearer {token}"},
                json=json,
            )
        return self._decode_response(response)

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
            raise FeishuApiError(msg, code=code if isinstance(code, int) else None)
        data = payload.get("data")
        return data if isinstance(data, dict) else payload


class _BorrowedAsyncClient:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def __aenter__(self) -> httpx.AsyncClient:
        return self._client

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

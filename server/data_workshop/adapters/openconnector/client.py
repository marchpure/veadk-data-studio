from __future__ import annotations

import json as json_module
import os
import re
from typing import Any, Literal
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse

import httpx


class OpenConnectorError(RuntimeError):
    def __init__(self, message: str, status_code: int = 502, detail: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail


class OpenConnectorClient:
    def __init__(
        self,
        base_url: str | None = None,
        public_url: str | None = None,
        admin_token: str | None = None,
        timeout_seconds: float = 15.0,
    ):
        self.base_url = (base_url or os.getenv("OPENCONNECTOR_URL", "")).rstrip("/")
        self.public_url = (public_url or os.getenv("OPENCONNECTOR_PUBLIC_URL", "") or self.base_url).rstrip("/")
        self.admin_token = admin_token or os.getenv("OPENCONNECTOR_ADMIN_TOKEN", "")
        self.timeout_seconds = timeout_seconds

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.admin_token)

    def _url(self, path: str, *, scope: Literal["admin", "runtime", "public"]) -> str:
        allowed = {
            "admin": path.startswith("/api/") or path in {"/docs", "/openapi.json"},
            "runtime": path == "/mcp" or path.startswith("/v1/"),
            "public": path == "/health",
        }
        if not allowed[scope]:
            raise ValueError(f"OpenConnector {scope} request cannot use path {path}")
        if not self.base_url:
            raise OpenConnectorError("OpenConnector is not configured", status_code=503)
        return urljoin(f"{self.base_url}/", path.lstrip("/"))

    def public_proxy_location(self, location: str) -> str:
        parsed_location = urlparse(location)
        if parsed_location.netloc:
            parsed_base = urlparse(self.base_url)
            if (parsed_location.scheme, parsed_location.netloc) != (parsed_base.scheme, parsed_base.netloc):
                raise OpenConnectorError("OpenConnector Console returned an unsafe redirect", status_code=502)
            path = parsed_location.path
            query = parsed_location.query
        else:
            path = parsed_location.path
            query = parsed_location.query
        public_location = f"/oc/{path.lstrip('/')}"
        return f"{public_location}?{query}" if query else public_location

    async def request_admin(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any = None,
        tenant_id: str,
    ) -> Any:
        if not self.admin_token:
            raise OpenConnectorError("OpenConnector is not configured", status_code=503)

        headers = {
            "Authorization": f"Bearer {self.admin_token}",
            "Accept": "application/json",
            "X-Tenant-ID": tenant_id,
        }
        return await self._request(method, self._url(path, scope="admin"), params=params, json=json, headers=headers)

    async def request_runtime(
        self,
        method: str,
        path: str,
        *,
        bearer_token: str,
        params: dict[str, Any] | None = None,
        json: Any = None,
        tenant_id: str,
    ) -> Any:
        if not self.base_url:
            raise OpenConnectorError("OpenConnector is not configured", status_code=503)
        if not bearer_token:
            raise OpenConnectorError("A user runtime credential is required", status_code=401)
        headers = {
            "Authorization": f"Bearer {bearer_token}",
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
            "X-Tenant-ID": tenant_id,
        }
        return await self._request(method, self._url(path, scope="runtime"), params=params, json=json, headers=headers)

    async def request_public(self, method: str, path: str) -> Any:
        if not self.base_url:
            raise OpenConnectorError("OpenConnector is not configured", status_code=503)
        return await self._request(
            method,
            self._url(path, scope="public"),
            headers={"Accept": "application/json"},
        )

    async def _request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any = None,
        headers: dict[str, str],
    ) -> Any:
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.request(method, url, params=params, json=json, headers=headers)
        except httpx.RequestError as exc:
            raise OpenConnectorError("OpenConnector is unavailable", detail={"reason": str(exc)}) from exc

        if response.status_code >= 400:
            try:
                detail = response.json()
            except ValueError:
                detail = {"message": response.text[:500]}
            raise OpenConnectorError(
                "OpenConnector rejected the request",
                status_code=response.status_code,
                detail=detail,
            )

        if response.status_code == 204:
            return None
        if response.headers.get("content-type", "").lower().startswith("text/event-stream"):
            return self._parse_sse_json(response.text)
        try:
            return response.json()
        except ValueError as exc:
            raise OpenConnectorError("OpenConnector returned an invalid response") from exc

    @staticmethod
    def _parse_sse_json(body: str) -> Any:
        payloads = [
            "\n".join(line[5:].lstrip() for line in event.splitlines() if line.startswith("data:"))
            for event in re.split(r"\r?\n\r?\n", body.strip())
        ]
        payloads = [payload for payload in payloads if payload]
        if len(payloads) != 1:
            raise OpenConnectorError("OpenConnector returned an invalid MCP event stream")
        try:
            return json_module.loads(payloads[0])
        except ValueError as exc:
            raise OpenConnectorError("OpenConnector returned invalid MCP event data") from exc

    async def proxy(
        self,
        method: str,
        path: str,
        *,
        query: bytes,
        body: bytes,
        content_type: str | None,
        tenant_id: str,
    ) -> httpx.Response:
        if not self.configured:
            raise OpenConnectorError("OpenConnector is not configured", status_code=503)

        safe_path = path.lstrip("/")
        if "://" in safe_path:
            raise OpenConnectorError("Invalid OpenConnector Console path", status_code=400)
        if safe_path == "mcp" or safe_path.startswith(("mcp/", "v1/")):
            raise OpenConnectorError(
                "OpenConnector runtime paths are not available through the admin Console proxy",
                status_code=403,
            )
        url = f"{self.base_url}/{safe_path}"
        if query:
            safe_query = urlencode(
                [
                    (key, value)
                    for key, value in parse_qsl(query.decode("ascii"), keep_blank_values=True)
                    if key.lower().replace("-", "_") not in {"access_token", "admin_token", "api_key", "token"}
                ]
            )
            if safe_query:
                url = f"{url}?{safe_query}"
        headers = {
            "Authorization": f"Bearer {self.admin_token}",
            "Accept": "text/html,application/xhtml+xml,application/json",
            "X-Forwarded-Prefix": "/oc",
            "X-Tenant-ID": tenant_id,
        }
        if content_type:
            headers["Content-Type"] = content_type
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds, follow_redirects=False) as client:
                return await client.request(method, url, content=body, headers=headers)
        except httpx.RequestError as exc:
            raise OpenConnectorError("OpenConnector Console is unavailable", detail={"reason": str(exc)}) from exc

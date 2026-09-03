from __future__ import annotations

import os
from typing import Any
from urllib.parse import urljoin, urlparse

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
        admin_token: str | None = None,
        timeout_seconds: float = 15.0,
    ):
        self.base_url = (base_url or os.getenv("OPENCONNECTOR_URL", "")).rstrip("/")
        self.admin_token = admin_token or os.getenv("OPENCONNECTOR_ADMIN_TOKEN", "")
        self.timeout_seconds = timeout_seconds

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.admin_token)

    def _url(self, path: str) -> str:
        if not path.startswith("/v1/"):
            raise ValueError("OpenConnector control-plane requests must use a versioned /v1 path")
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

    async def request(
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
        }
        headers["X-Tenant-ID"] = tenant_id
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.request(method, self._url(path), params=params, json=json, headers=headers)
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
        try:
            return response.json()
        except ValueError as exc:
            raise OpenConnectorError("OpenConnector returned an invalid response") from exc

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
        url = f"{self.base_url}/{safe_path}"
        if query:
            url = f"{url}?{query.decode('ascii')}"
        headers = {
            "Authorization": f"Bearer {self.admin_token}",
            "Accept": "text/html,application/xhtml+xml,application/json",
            "X-Tenant-ID": tenant_id,
        }
        if content_type:
            headers["Content-Type"] = content_type
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds, follow_redirects=False) as client:
                return await client.request(method, url, content=body, headers=headers)
        except httpx.RequestError as exc:
            raise OpenConnectorError("OpenConnector Console is unavailable", detail={"reason": str(exc)}) from exc

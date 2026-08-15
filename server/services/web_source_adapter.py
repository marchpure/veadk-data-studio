from __future__ import annotations

import hashlib
import html
import ipaddress
import re
import socket
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse, urlunparse

import httpx

from server.services.source_connectors import ConnectorError


@dataclass(frozen=True)
class WebCapturedPage:
    raw_bytes: bytes
    content_text: str
    external_revision: str
    metadata: dict
    parser_version: str
    raw_storage_uri: str


class WebSourceAdapter:
    max_bytes = 5 * 1024 * 1024
    max_redirects = 5
    allowed_content_types = {
        "text/html",
        "application/xhtml+xml",
        "text/plain",
        "text/markdown",
    }

    def __init__(self, *, transport: httpx.AsyncBaseTransport | None = None):
        self.transport = transport

    async def capture(self, url: str) -> WebCapturedPage:
        redirects: list[str] = []
        current_url = self._validate_url(url)
        canonical_url = current_url
        verify_ssl = self._get_ssl_verify_setting()

        async with httpx.AsyncClient(
            timeout=20.0,
            follow_redirects=False,
            verify=verify_ssl,
            transport=self.transport,
        ) as client:
            for _ in range(self.max_redirects + 1):
                try:
                    async with client.stream("GET", current_url) as response:
                        if response.status_code in {301, 302, 303, 307, 308}:
                            location = response.headers.get("location")
                            if not location:
                                raise ConnectorError("Web redirect response is missing Location header", code="web_fetch_failed", permanent=True)
                            next_url = self._validate_url(urljoin(current_url, location))
                            redirects.append(next_url)
                            current_url = next_url
                            continue

                        if response.status_code >= 400:
                            raise ConnectorError(f"Web page returned HTTP {response.status_code}", code="source_unavailable", permanent=True)

                        content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                        if content_type and content_type not in self.allowed_content_types:
                            raise ConnectorError(f"Unsupported web content type: {content_type}", code="unsupported_web_content_type", permanent=True)

                        content_length = response.headers.get("content-length")
                        if content_length and int(content_length) > self.max_bytes:
                            raise ConnectorError("Web page is too large; confirmation required", code="large_file_confirmation_required", permanent=True)

                        raw_bytes = await self._read_limited_response(response)
                        final_url = str(response.url) if response.url else current_url
                        headers = dict(response.headers)
                        status_code = response.status_code
                        break
                except httpx.RequestError as exc:
                    raise ConnectorError(f"Failed to fetch web page: {exc}", code="web_fetch_failed") from exc
                break
            else:
                raise ConnectorError("Web page has too many redirects", code="too_many_redirects", permanent=True)

        if not raw_bytes:
            raise ConnectorError("Web page returned an empty response", code="source_unavailable", permanent=True)

        text, title = self._extract_text(raw_bytes, content_type=content_type)
        if not text.strip():
            raise ConnectorError("Web page text extraction produced no content", code="parser_no_text", permanent=True)

        content_hash = hashlib.sha256(raw_bytes).hexdigest()
        etag = headers.get("etag")
        last_modified = headers.get("last-modified")
        revision = etag or last_modified or f"sha256:{content_hash}"
        return WebCapturedPage(
            raw_bytes=raw_bytes,
            content_text=text,
            external_revision=revision,
            metadata={
                "provider": "web",
                "initial_url": url,
                "canonical_url": canonical_url,
                "final_url": final_url,
                "redirect_chain": redirects,
                "status_code": status_code,
                "content_type": content_type or None,
                "etag": etag,
                "last_modified": last_modified,
                "title": title,
                "raw_size": len(raw_bytes),
            },
            parser_version="web-html-parser-v1" if content_type != "text/plain" else "web-text-parser-v1",
            raw_storage_uri=f"web://sha256/{content_hash}",
        )

    async def _read_limited_response(self, response: httpx.Response) -> bytes:
        chunks = bytearray()
        async for chunk in response.aiter_bytes(chunk_size=64 * 1024):
            chunks.extend(chunk)
            if len(chunks) > self.max_bytes:
                raise ConnectorError("Web page is too large; confirmation required", code="large_file_confirmation_required", permanent=True)
        return bytes(chunks)

    def _validate_url(self, url: str) -> str:
        parsed = urlparse(url.strip())
        if parsed.scheme not in {"http", "https"}:
            raise ConnectorError("Only HTTP/HTTPS web URLs are supported", code="invalid_url", permanent=True)
        if not parsed.hostname:
            raise ConnectorError("Web URL is missing a hostname", code="invalid_url", permanent=True)
        self._validate_hostname(parsed.hostname)
        return self._canonicalize_url(parsed)

    def _canonicalize_url(self, parsed) -> str:
        scheme = parsed.scheme.lower()
        hostname = (parsed.hostname or "").lower()
        netloc = hostname
        if parsed.port and not ((scheme == "http" and parsed.port == 80) or (scheme == "https" and parsed.port == 443)):
            netloc = f"{hostname}:{parsed.port}"
        path = parsed.path or "/"
        return urlunparse((scheme, netloc, path, "", parsed.query, ""))

    def _validate_hostname(self, hostname: str) -> None:
        if hostname.lower() == "localhost":
            raise ConnectorError("Access to local web URLs is not allowed", code="blocked_private_url", permanent=True)
        try:
            ip = ipaddress.ip_address(hostname)
            self._validate_ip(ip)
            return
        except ValueError:
            pass

        try:
            addr_infos = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise ConnectorError(f"Web URL hostname cannot be resolved: {hostname}", code="dns_resolution_failed") from exc
        if not addr_infos:
            raise ConnectorError(f"Web URL hostname cannot be resolved: {hostname}", code="dns_resolution_failed")
        for addr_info in addr_infos:
            address = addr_info[4][0]
            self._validate_ip(ipaddress.ip_address(address))

    def _validate_ip(self, ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> None:
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            raise ConnectorError(f"Access to private or non-routable address is not allowed: {ip}", code="blocked_private_url", permanent=True)

    def _extract_text(self, raw_bytes: bytes, *, content_type: str) -> tuple[str, str | None]:
        source = raw_bytes.decode("utf-8", errors="replace")
        if content_type in {"text/plain", "text/markdown"}:
            text = re.sub(r"\s+\n", "\n", source).strip()
            return text[:100000], None

        title_match = re.search(r"(?is)<title[^>]*>(.*?)</title>", source)
        title = self._clean_text(title_match.group(1)) if title_match else None
        body_match = re.search(r"(?is)<body[^>]*>(.*?)</body>", source)
        body = body_match.group(1) if body_match else source
        body = re.sub(r"(?is)<(script|style|noscript|svg|canvas).*?>.*?</\1>", " ", body)
        body = re.sub(r"(?i)<br\s*/?>", "\n", body)
        body = re.sub(r"(?i)</(p|div|section|article|header|footer|li|tr|h[1-6])>", "\n", body)
        body = re.sub(r"(?s)<[^>]+>", " ", body)
        text = self._clean_text(body)
        return text[:100000], title

    def _clean_text(self, value: str) -> str:
        value = html.unescape(value)
        value = re.sub(r"[ \t\r\f\v]+", " ", value)
        value = re.sub(r"\n\s*\n\s*\n+", "\n\n", value)
        return value.strip()

    def _get_ssl_verify_setting(self) -> bool:
        from server.utils.config_loader import is_self_hosted

        return is_self_hosted()

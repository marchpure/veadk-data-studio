from __future__ import annotations

import httpx
import pytest

from server.services.source_connectors import ConnectorError
from server.services.web_source_adapter import WebSourceAdapter

pytestmark = pytest.mark.asyncio


def _transport(handler):
    return httpx.MockTransport(handler)


async def test_web_adapter_captures_html_snapshot_with_redirect_metadata(monkeypatch):
    monkeypatch.setattr(WebSourceAdapter, "_validate_hostname", lambda self, hostname: None)

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == "https://example.com/start":
            return httpx.Response(302, headers={"location": "/final"}, request=request)
        assert str(request.url) == "https://example.com/final"
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8", "etag": "etag-1"},
            content=b"<html><title>Report</title><body><script>bad()</script><h1>Revenue</h1><p>East grew.</p></body></html>",
            request=request,
        )

    captured = await WebSourceAdapter(transport=_transport(handler)).capture("https://example.com/start")

    assert captured.external_revision == "etag-1"
    assert captured.metadata["final_url"] == "https://example.com/final"
    assert captured.metadata["redirect_chain"] == ["https://example.com/final"]
    assert captured.metadata["title"] == "Report"
    assert "Revenue" in captured.content_text
    assert "bad()" not in captured.content_text
    assert captured.raw_storage_uri.startswith("web://sha256/")


async def test_web_adapter_rejects_unsupported_mime_and_private_urls(monkeypatch):
    with pytest.raises(ConnectorError) as blocked:
        await WebSourceAdapter().capture("http://127.0.0.1:8080/admin")
    assert blocked.value.code == "blocked_private_url"

    monkeypatch.setattr(WebSourceAdapter, "_validate_hostname", lambda self, hostname: None)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "application/octet-stream"},
            content=b"binary",
            request=request,
        )

    with pytest.raises(ConnectorError) as unsupported:
        await WebSourceAdapter(transport=_transport(handler)).capture("https://example.com/file.bin")
    assert unsupported.value.code == "unsupported_web_content_type"


async def test_web_adapter_enforces_content_length_and_streaming_size_limits(monkeypatch):
    monkeypatch.setattr(WebSourceAdapter, "_validate_hostname", lambda self, hostname: None)

    def length_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/plain", "content-length": "9"},
            content=b"too large",
            request=request,
        )

    length_adapter = WebSourceAdapter(transport=_transport(length_handler))
    length_adapter.max_bytes = 8
    with pytest.raises(ConnectorError) as content_length:
        await length_adapter.capture("https://example.com/large")
    assert content_length.value.code == "large_file_confirmation_required"

    def streaming_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/plain"},
            content=b"123456789",
            request=request,
        )

    streaming_adapter = WebSourceAdapter(transport=_transport(streaming_handler))
    streaming_adapter.max_bytes = 8
    with pytest.raises(ConnectorError) as streaming:
        await streaming_adapter.capture("https://example.com/large")
    assert streaming.value.code == "large_file_confirmation_required"

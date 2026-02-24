"""Tests for the WARC record parser."""

import gzip

from apps.cc_index.warc_parse import parse_warc_record


def _make_warc_response(url: str, html: str, status: int = 200) -> bytes:
    """Build a synthetic gzipped WARC response record."""
    http_body = html.encode("utf-8")
    http_response = (
        f"HTTP/1.1 {status} OK\r\n"
        f"Content-Type: text/html; charset=utf-8\r\n"
        f"Content-Length: {len(http_body)}\r\n"
        f"\r\n"
    ).encode("utf-8") + http_body

    warc_headers = (
        f"WARC/1.0\r\n"
        f"WARC-Type: response\r\n"
        f"WARC-Target-URI: {url}\r\n"
        f"Content-Length: {len(http_response)}\r\n"
        f"\r\n"
    ).encode("utf-8")

    raw = warc_headers + http_response
    return gzip.compress(raw)


def _make_warc_non_response(warc_type: str = "warcinfo") -> bytes:
    """Build a non-response WARC record."""
    warc_headers = (f"WARC/1.0\r\nWARC-Type: {warc_type}\r\nWARC-Target-URI: \r\n\r\n").encode(
        "utf-8"
    )
    body = b"some metadata content"
    raw = warc_headers + body
    return gzip.compress(raw)


def test_parse_valid_response():
    gz = _make_warc_response("https://example.rw/page", "<html><body>Hello</body></html>")
    result = parse_warc_record(gz)

    assert result.ok
    assert result.warc_type == "response"
    assert result.target_url == "https://example.rw/page"
    assert result.http_status == 200
    assert result.http_headers["content-type"] == "text/html; charset=utf-8"
    assert b"Hello" in result.body


def test_parse_extracts_html_body():
    html = "<html><body><p>Mu Rwanda uburezi ni ingenzi</p></body></html>"
    gz = _make_warc_response("https://umuseke.rw/article", html)
    result = parse_warc_record(gz)

    assert result.ok
    assert result.body == html.encode("utf-8")


def test_parse_non_response_record():
    gz = _make_warc_non_response("warcinfo")
    result = parse_warc_record(gz)

    assert not result.ok
    assert "not_response" in result.error
    assert result.warc_type == "warcinfo"


def test_parse_bad_gzip():
    result = parse_warc_record(b"not gzip data")
    assert not result.ok
    assert "decompress_failed" in result.error


def test_parse_empty_gzip():
    gz = gzip.compress(b"")
    result = parse_warc_record(gz)
    assert not result.ok
    assert result.error == "no_warc_headers"


def test_parse_http_status_404():
    gz = _make_warc_response("https://a.rw/missing", "<html>Not Found</html>", status=404)
    result = parse_warc_record(gz)

    assert result.ok
    assert result.http_status == 404
    assert b"Not Found" in result.body


def test_parse_preserves_binary_body():
    """Non-UTF8 body bytes are preserved as-is."""
    http_body = b"\xff\xfe<html>binary</html>"
    http_response = b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n" + http_body
    warc_headers = b"WARC/1.0\r\nWARC-Type: response\r\nWARC-Target-URI: https://a.rw/\r\n\r\n"
    gz = gzip.compress(warc_headers + http_response)
    result = parse_warc_record(gz)

    assert result.ok
    assert result.body == http_body

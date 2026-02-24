"""Parse a single gzipped WARC record into HTTP headers + HTML body."""

import gzip
from dataclasses import dataclass, field

from apps.common.logging import get_logger

log = get_logger(__name__)


@dataclass
class ParsedWARCRecord:
    """A parsed WARC record containing the HTTP response body."""

    warc_type: str = ""
    target_url: str = ""
    http_status: int = 0
    http_headers: dict[str, str] = field(default_factory=dict)
    body: bytes = b""
    ok: bool = True
    error: str = ""


def parse_warc_record(raw_gz: bytes) -> ParsedWARCRecord:
    """Decompress and parse a single gzipped WARC record.

    Structure of a WARC response record:
    1. WARC headers (terminated by \\r\\n\\r\\n)
    2. HTTP status line + response headers (terminated by \\r\\n\\r\\n)
    3. HTTP body (the HTML content)
    """
    try:
        raw = gzip.decompress(raw_gz)
    except (gzip.BadGzipFile, OSError, EOFError) as exc:
        return ParsedWARCRecord(ok=False, error=f"decompress_failed: {exc}")

    # Split WARC headers from the rest
    separator = b"\r\n\r\n"
    warc_end = raw.find(separator)
    if warc_end == -1:
        return ParsedWARCRecord(ok=False, error="no_warc_headers")

    warc_header_bytes = raw[:warc_end]
    after_warc = raw[warc_end + len(separator) :]

    # Parse WARC headers
    warc_headers = _parse_headers(warc_header_bytes)
    warc_type = warc_headers.get("warc-type", "")
    target_url = warc_headers.get("warc-target-uri", "")

    if warc_type != "response":
        return ParsedWARCRecord(
            warc_type=warc_type,
            target_url=target_url,
            ok=False,
            error=f"not_response: {warc_type}",
        )

    # Split HTTP status+headers from body
    http_end = after_warc.find(separator)
    if http_end == -1:
        return ParsedWARCRecord(
            warc_type=warc_type,
            target_url=target_url,
            ok=False,
            error="no_http_headers",
        )

    http_header_bytes = after_warc[:http_end]
    body = after_warc[http_end + len(separator) :]

    # Parse HTTP status line and headers
    http_status, http_headers = _parse_http_headers(http_header_bytes)

    return ParsedWARCRecord(
        warc_type=warc_type,
        target_url=target_url,
        http_status=http_status,
        http_headers=http_headers,
        body=body,
    )


def _parse_headers(header_bytes: bytes) -> dict[str, str]:
    """Parse WARC-style headers into a dict (lowercase keys)."""
    headers: dict[str, str] = {}
    for line in header_bytes.decode("utf-8", errors="replace").splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            headers[key.strip().lower()] = value.strip()
    return headers


def _parse_http_headers(header_bytes: bytes) -> tuple[int, dict[str, str]]:
    """Parse HTTP status line + headers. Returns (status_code, headers_dict)."""
    lines = header_bytes.decode("utf-8", errors="replace").splitlines()
    status = 0
    headers: dict[str, str] = {}

    if lines:
        # First line: "HTTP/1.1 200 OK"
        parts = lines[0].split(None, 2)
        if len(parts) >= 2:
            try:
                status = int(parts[1])
            except ValueError:
                pass

        for line in lines[1:]:
            if ":" in line:
                key, _, value = line.partition(":")
                headers[key.strip().lower()] = value.strip()

    return status, headers

"""Tests for the Wayback Machine page fetcher."""

from unittest.mock import MagicMock, patch

import requests as req

from apps.common.config_types import WaybackConfig
from apps.wayback.cdx_client import WaybackRecord
from apps.wayback.fetch import WaybackFetchResult, fetch_wayback_page


def _record() -> WaybackRecord:
    return WaybackRecord(
        timestamp="20231215120000",
        original_url="https://igihe.com/article1",
        status_code="200",
        mime_type="text/html",
        length=5000,
    )


def _cfg() -> WaybackConfig:
    return WaybackConfig(
        fetch_timeout_s=5,
        fetch_max_retries=2,
        fetch_retry_backoff_s=0,
    )


@patch("apps.wayback.fetch.requests.get")
def test_fetch_wayback_page_ok(mock_get: MagicMock) -> None:
    resp = MagicMock()
    resp.status_code = 200
    resp.content = b"<html>hello</html>"
    mock_get.return_value = resp

    result = fetch_wayback_page(_record(), _cfg())
    assert result.ok
    assert result.html_bytes == b"<html>hello</html>"
    assert result.error == ""


@patch("apps.wayback.fetch.requests.get")
def test_fetch_wayback_page_rate_limited_then_ok(mock_get: MagicMock) -> None:
    rate_limited = MagicMock()
    rate_limited.status_code = 429

    ok_resp = MagicMock()
    ok_resp.status_code = 200
    ok_resp.content = b"<html>ok</html>"

    mock_get.side_effect = [rate_limited, ok_resp]

    result = fetch_wayback_page(_record(), _cfg())
    assert result.ok
    assert mock_get.call_count == 2


@patch("apps.wayback.fetch.requests.get")
def test_fetch_wayback_page_server_error_retries(mock_get: MagicMock) -> None:
    error_resp = MagicMock()
    error_resp.status_code = 500
    mock_get.return_value = error_resp

    result = fetch_wayback_page(_record(), _cfg())
    assert not result.ok
    assert result.error == "max_retries_exceeded"
    assert mock_get.call_count == 2  # max_retries=2


@patch("apps.wayback.fetch.requests.get")
def test_fetch_wayback_page_404_no_retry(mock_get: MagicMock) -> None:
    resp = MagicMock()
    resp.status_code = 404
    mock_get.return_value = resp

    result = fetch_wayback_page(_record(), _cfg())
    assert not result.ok
    assert result.error == "http_404"
    assert mock_get.call_count == 1  # No retry on 4xx


@patch("apps.wayback.fetch.requests.get")
def test_fetch_wayback_page_timeout(mock_get: MagicMock) -> None:
    mock_get.side_effect = req.exceptions.Timeout("timeout")

    result = fetch_wayback_page(_record(), _cfg())
    assert not result.ok
    assert result.error == "timeout"


@patch("apps.wayback.fetch.requests.get")
def test_fetch_wayback_page_connection_error(mock_get: MagicMock) -> None:
    mock_get.side_effect = req.exceptions.ConnectionError("refused")

    result = fetch_wayback_page(_record(), _cfg())
    assert not result.ok
    assert result.error == "connection_error"


def test_wayback_fetch_result_default() -> None:
    result = WaybackFetchResult()
    assert result.ok
    assert result.html_bytes == b""
    assert result.error == ""

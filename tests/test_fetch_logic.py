"""Tests for targeted crawler HTTP fetcher (mocked)."""

from unittest.mock import MagicMock, patch

import pytest

from apps.common.config_types import TargetedConfig
from apps.targeted_crawler.fetch import FetchResult, fetch_url


@pytest.fixture
def cfg():
    return TargetedConfig(
        max_retries=2,
        retry_backoff_s=0,
        request_timeout_s=5,
        max_response_bytes=1000,
    )


def _mock_response(
    status=200, content=b"<html>hello</html>", content_type="text/html", url="https://example.com"
):
    resp = MagicMock()
    resp.status_code = status
    resp.url = url
    resp.headers = {"Content-Type": content_type}
    resp.iter_content = MagicMock(return_value=iter([content]))
    return resp


@patch("apps.targeted_crawler.fetch.requests.get")
def test_fetch_success(mock_get, cfg):
    mock_get.return_value = _mock_response()
    result = fetch_url("https://example.com", cfg)
    assert result.ok
    assert result.status_code == 200
    assert result.content == b"<html>hello</html>"
    assert result.content_type == "text/html"


@patch("apps.targeted_crawler.fetch.requests.get")
def test_fetch_follows_redirects(mock_get, cfg):
    mock_get.return_value = _mock_response(url="https://example.com/final")
    result = fetch_url("https://example.com", cfg)
    assert result.ok
    assert result.final_url == "https://example.com/final"


@patch("apps.targeted_crawler.fetch.requests.get")
def test_fetch_rejects_disallowed_content_type(mock_get, cfg):
    mock_get.return_value = _mock_response(content_type="application/pdf")
    result = fetch_url("https://example.com/file.pdf", cfg)
    assert not result.ok
    assert "disallowed_content_type" in result.error


@patch("apps.targeted_crawler.fetch.requests.get")
def test_fetch_404_no_retry(mock_get, cfg):
    mock_get.return_value = _mock_response(status=404)
    result = fetch_url("https://example.com/gone", cfg)
    assert not result.ok
    assert result.error == "http_404"
    assert mock_get.call_count == 1  # No retry for 4xx


@patch("apps.targeted_crawler.fetch.requests.get")
def test_fetch_500_retries(mock_get, cfg):
    mock_get.return_value = _mock_response(status=500)
    result = fetch_url("https://example.com/error", cfg)
    assert not result.ok
    assert mock_get.call_count == cfg.max_retries


@patch("apps.targeted_crawler.fetch.requests.get")
def test_fetch_timeout_retries(mock_get, cfg):
    import requests as req

    mock_get.side_effect = req.exceptions.Timeout("timeout")
    result = fetch_url("https://example.com/slow", cfg)
    assert not result.ok
    assert result.error == "timeout"
    assert mock_get.call_count == cfg.max_retries


@patch("apps.targeted_crawler.fetch.requests.get")
def test_fetch_response_too_large(mock_get, cfg):
    big_content = b"x" * 2000  # > max_response_bytes=1000
    mock_get.return_value = _mock_response(content=big_content)
    result = fetch_url("https://example.com/huge", cfg)
    assert not result.ok
    assert result.error == "response_too_large"


@patch("apps.targeted_crawler.fetch.requests.get")
def test_fetch_connection_error_retries(mock_get, cfg):
    import requests as req

    mock_get.side_effect = req.exceptions.ConnectionError("refused")
    result = fetch_url("https://example.com/down", cfg)
    assert not result.ok
    assert result.error == "connection_error"
    assert mock_get.call_count == cfg.max_retries


@patch("apps.targeted_crawler.fetch.requests.get")
def test_fetch_content_type_with_charset(mock_get, cfg):
    mock_get.return_value = _mock_response(content_type="text/html; charset=utf-8")
    result = fetch_url("https://example.com", cfg)
    assert result.ok
    assert result.content_type == "text/html"


@patch("apps.targeted_crawler.fetch.requests.get")
def test_fetch_result_properties(mock_get, cfg):
    result = FetchResult(url="https://x.com", error="something")
    assert not result.ok
    result2 = FetchResult(url="https://x.com", status_code=200)
    assert result2.ok

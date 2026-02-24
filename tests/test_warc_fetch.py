"""Tests for the WARC byte-range fetcher."""

from unittest.mock import MagicMock, patch

from apps.cc_index.warc_fetch import fetch_warc_record
from apps.common.config_types import CCIndexConfig

_BASE_CFG = CCIndexConfig(
    warc_timeout_s=5,
    warc_max_retries=2,
    warc_retry_backoff_s=0,
    user_agent="test/0.1",
)


@patch("apps.cc_index.warc_fetch.requests.get")
def test_fetch_success_206(mock_get):
    resp = MagicMock()
    resp.status_code = 206
    resp.content = b"fake-warc-data"
    mock_get.return_value = resp

    result = fetch_warc_record("path/to/warc.gz", 1000, 500, _BASE_CFG)
    assert result.ok
    assert result.raw_data == b"fake-warc-data"

    # Verify Range header
    call_kwargs = mock_get.call_args
    assert call_kwargs[1]["headers"]["Range"] == "bytes=1000-1499"


@patch("apps.cc_index.warc_fetch.requests.get")
def test_fetch_success_200(mock_get):
    resp = MagicMock()
    resp.status_code = 200
    resp.content = b"warc-data"
    mock_get.return_value = resp

    result = fetch_warc_record("path/to/warc.gz", 0, 100, _BASE_CFG)
    assert result.ok
    assert result.raw_data == b"warc-data"


@patch("apps.cc_index.warc_fetch.requests.get")
def test_fetch_404(mock_get):
    resp = MagicMock()
    resp.status_code = 404
    mock_get.return_value = resp

    result = fetch_warc_record("missing.gz", 0, 100, _BASE_CFG)
    assert not result.ok
    assert result.error == "http_404"


@patch("apps.cc_index.warc_fetch.requests.get")
def test_fetch_retries_on_500(mock_get):
    fail_resp = MagicMock()
    fail_resp.status_code = 500

    ok_resp = MagicMock()
    ok_resp.status_code = 206
    ok_resp.content = b"data"

    mock_get.side_effect = [fail_resp, ok_resp]

    result = fetch_warc_record("path.gz", 0, 100, _BASE_CFG)
    assert result.ok
    assert mock_get.call_count == 2


@patch("apps.cc_index.warc_fetch.requests.get")
def test_fetch_connection_error(mock_get):
    import requests

    mock_get.side_effect = requests.ConnectionError("refused")

    result = fetch_warc_record("path.gz", 0, 100, _BASE_CFG)
    assert not result.ok
    assert result.error == "connection_error"


@patch("apps.cc_index.warc_fetch.requests.get")
def test_fetch_max_retries_exceeded(mock_get):
    resp = MagicMock()
    resp.status_code = 500
    mock_get.return_value = resp

    result = fetch_warc_record("path.gz", 0, 100, _BASE_CFG)
    assert not result.ok
    assert result.error == "max_retries_exceeded"

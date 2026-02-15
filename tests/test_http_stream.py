"""Tests for streaming HTTP downloader (mocked)."""

from unittest.mock import MagicMock, patch

import pytest
import requests

from apps.cc_miner.http_stream import stream_download
from apps.common.config_types import AppConfig


def _cfg() -> AppConfig:
    cfg = AppConfig()
    cfg.cc.max_retries = 3
    cfg.cc.retry_backoff_s = 0  # no waiting in tests
    cfg.cc.request_timeout_s = 10
    cfg.cc.user_agent = "test/0.1"
    return cfg


@patch("apps.cc_miner.http_stream.requests.get")
def test_successful_download(mock_get):
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.iter_content.return_value = [b"chunk1", b"chunk2"]
    mock_get.return_value = mock_resp

    chunks = list(stream_download("https://example.com/file.gz", _cfg()))
    assert chunks == [b"chunk1", b"chunk2"]
    mock_get.assert_called_once()


@patch("apps.cc_miner.http_stream.requests.get")
def test_retries_on_failure(mock_get):
    mock_get.side_effect = [
        requests.ConnectionError("fail"),
        requests.ConnectionError("fail"),
        MagicMock(
            raise_for_status=MagicMock(),
            iter_content=MagicMock(return_value=[b"ok"]),
        ),
    ]

    chunks = list(stream_download("https://example.com/file.gz", _cfg()))
    assert chunks == [b"ok"]
    assert mock_get.call_count == 3


@patch("apps.cc_miner.http_stream.requests.get")
def test_all_retries_exhausted(mock_get):
    mock_get.side_effect = requests.ConnectionError("fail")

    with pytest.raises(ConnectionError):
        list(stream_download("https://example.com/file.gz", _cfg()))
    assert mock_get.call_count == 3

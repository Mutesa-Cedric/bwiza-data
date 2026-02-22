"""Tests for Wikipedia dump downloader."""

from unittest.mock import MagicMock, patch

from apps.wiki_miner.download import MAX_EXPECTED_BYTES, download_rw_dump


def _mock_head(size: int) -> MagicMock:
    resp = MagicMock()
    resp.headers = {"Content-Length": str(size)}
    resp.raise_for_status = MagicMock()
    return resp


def _mock_get(content: bytes) -> MagicMock:
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.iter_content = MagicMock(return_value=[content])
    return resp


@patch("apps.wiki_miner.download.requests")
def test_download_creates_file(mock_requests, tmp_path):
    data = b"fake-bz2-dump-content"
    mock_requests.head.return_value = _mock_head(len(data))
    mock_requests.get.return_value = _mock_get(data)

    path = download_rw_dump(str(tmp_path / "wiki"))

    assert path.exists()
    assert path.read_bytes() == data
    assert path.name == "rwwiki-latest-pages-articles.xml.bz2"


@patch("apps.wiki_miner.download.requests")
def test_download_skips_if_exists(mock_requests, tmp_path):
    out_dir = tmp_path / "wiki"
    out_dir.mkdir()
    dest = out_dir / "rwwiki-latest-pages-articles.xml.bz2"
    data = b"existing-dump"
    dest.write_bytes(data)

    mock_requests.head.return_value = _mock_head(len(data))

    path = download_rw_dump(str(out_dir))

    assert path == dest
    mock_requests.get.assert_not_called()


@patch("apps.wiki_miner.download.requests")
def test_download_redownloads_if_size_mismatch(mock_requests, tmp_path):
    out_dir = tmp_path / "wiki"
    out_dir.mkdir()
    dest = out_dir / "rwwiki-latest-pages-articles.xml.bz2"
    dest.write_bytes(b"old")

    new_data = b"new-dump-content"
    mock_requests.head.return_value = _mock_head(len(new_data))
    mock_requests.get.return_value = _mock_get(new_data)

    path = download_rw_dump(str(out_dir))
    assert path.read_bytes() == new_data


@patch("apps.wiki_miner.download.requests")
def test_download_rejects_oversized_dump(mock_requests, tmp_path):
    mock_requests.head.return_value = _mock_head(MAX_EXPECTED_BYTES + 1)

    try:
        download_rw_dump(str(tmp_path / "wiki"))
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "exceeds" in str(e)


@patch("apps.wiki_miner.download.requests")
def test_download_custom_url(mock_requests, tmp_path):
    data = b"custom"
    mock_requests.head.return_value = _mock_head(len(data))
    mock_requests.get.return_value = _mock_get(data)

    download_rw_dump(str(tmp_path / "wiki"), url="https://example.com/dump.xml.bz2")

    mock_requests.get.assert_called_once()
    call_url = mock_requests.get.call_args[0][0]
    assert call_url == "https://example.com/dump.xml.bz2"

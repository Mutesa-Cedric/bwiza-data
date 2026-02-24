"""Tests for WET file URL enumeration."""

import gzip
from unittest.mock import MagicMock, patch

from apps.cc_index.wet_enumerate import enumerate_wet_urls


def _make_paths_gz(paths: list[str]) -> bytes:
    """Create a gzipped wet.paths content."""
    content = "\n".join(paths).encode("utf-8")
    return gzip.compress(content)


@patch("apps.cc_index.wet_enumerate.requests.get")
def test_enumerate_parses_paths(mock_get):
    paths = [
        "crawl-data/CC-MAIN-2025-51/segments/123/wet/CC-MAIN-00001.warc.wet.gz",
        "crawl-data/CC-MAIN-2025-51/segments/123/wet/CC-MAIN-00002.warc.wet.gz",
        "crawl-data/CC-MAIN-2025-51/segments/456/wet/CC-MAIN-00003.warc.wet.gz",
    ]
    resp = MagicMock()
    resp.content = _make_paths_gz(paths)
    resp.raise_for_status = MagicMock()
    mock_get.return_value = resp

    urls = enumerate_wet_urls("CC-MAIN-2025-51")

    assert len(urls) == 3
    assert all(url.startswith("https://data.commoncrawl.org/") for url in urls)
    assert "CC-MAIN-00001" in urls[0]
    assert "CC-MAIN-00003" in urls[2]


@patch("apps.cc_index.wet_enumerate.requests.get")
def test_enumerate_skips_blank_lines(mock_get):
    paths = [
        "crawl-data/CC-MAIN-2025-51/segments/123/wet/file1.wet.gz",
        "",
        "  ",
        "crawl-data/CC-MAIN-2025-51/segments/123/wet/file2.wet.gz",
    ]
    resp = MagicMock()
    resp.content = _make_paths_gz(paths)
    resp.raise_for_status = MagicMock()
    mock_get.return_value = resp

    urls = enumerate_wet_urls("CC-MAIN-2025-51")
    assert len(urls) == 2


@patch("apps.cc_index.wet_enumerate.requests.get")
def test_enumerate_empty_response(mock_get):
    resp = MagicMock()
    resp.content = gzip.compress(b"")
    resp.raise_for_status = MagicMock()
    mock_get.return_value = resp

    urls = enumerate_wet_urls("CC-MAIN-2025-51")
    assert urls == []

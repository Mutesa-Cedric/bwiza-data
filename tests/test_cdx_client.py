"""Tests for the CC CDX API client."""

import json
from unittest.mock import MagicMock, patch

from apps.cc_index.cdx_client import (
    CDXRecord,
    build_record_list,
    discover_crawls,
    query_cdx,
)
from apps.common.config_types import CCIndexConfig


def _mock_collinfo():
    """Fake collinfo.json response."""
    return [
        {"id": "CC-MAIN-2025-51", "name": "December 2025"},
        {"id": "CC-MAIN-2025-40", "name": "October 2025"},
        {"id": "CC-MAIN-2025-22", "name": "May 2025"},
        {"id": "CC-MAIN-2024-51", "name": "December 2024"},
        {"id": "CC-MAIN-2024-33", "name": "August 2024"},
        {"id": "CC-MAIN-2024-10", "name": "March 2024"},
        {"id": "CC-MAIN-2023-50", "name": "December 2023"},
    ]


def _cdx_ndjson_lines():
    """Fake CDX NDJSON response."""
    records = [
        {
            "url": "https://igihe.com/article1",
            "filename": "crawl-data/CC-MAIN-2025-51/segments/123/warc/CC-MAIN-00001.warc.gz",
            "offset": "1000",
            "length": "5000",
            "status": "200",
            "mime": "text/html",
            "digest": "abc123",
        },
        {
            "url": "https://umuseke.rw/news",
            "filename": "crawl-data/CC-MAIN-2025-51/segments/456/warc/CC-MAIN-00002.warc.gz",
            "offset": "2000",
            "length": "3000",
            "status": "200",
            "mime": "text/html",
            "digest": "def456",
        },
    ]
    return "\n".join(json.dumps(r) for r in records)


@patch("apps.cc_index.cdx_client.requests.get")
def test_discover_crawls_filters_by_date(mock_get):
    resp = MagicMock()
    resp.json.return_value = _mock_collinfo()
    resp.raise_for_status = MagicMock()
    mock_get.return_value = resp

    result = discover_crawls(min_date="2025-01", max_crawls=10)
    assert all(c.startswith("CC-MAIN-2025") for c in result)
    assert len(result) == 3


@patch("apps.cc_index.cdx_client.requests.get")
def test_discover_crawls_limits_count(mock_get):
    resp = MagicMock()
    resp.json.return_value = _mock_collinfo()
    resp.raise_for_status = MagicMock()
    mock_get.return_value = resp

    result = discover_crawls(max_crawls=2)
    assert len(result) == 2
    # Should be newest first
    assert result[0] == "CC-MAIN-2025-51"


@patch("apps.cc_index.cdx_client.requests.get")
def test_discover_crawls_date_range(mock_get):
    resp = MagicMock()
    resp.json.return_value = _mock_collinfo()
    resp.raise_for_status = MagicMock()
    mock_get.return_value = resp

    result = discover_crawls(min_date="2024-01", max_date="2024-99", max_crawls=10)
    assert all("2024" in c for c in result)
    assert len(result) == 3


@patch("apps.cc_index.cdx_client.requests.get")
def test_query_cdx_parses_ndjson(mock_get):
    cfg = CCIndexConfig(cdx_page_size=1, cdx_rate_limit_s=0)

    # First call: showNumPages
    num_pages_resp = MagicMock()
    num_pages_resp.text = "1"
    num_pages_resp.status_code = 200
    num_pages_resp.raise_for_status = MagicMock()

    # Second call: actual page
    page_resp = MagicMock()
    page_resp.text = _cdx_ndjson_lines()
    page_resp.status_code = 200
    page_resp.raise_for_status = MagicMock()

    mock_get.side_effect = [num_pages_resp, page_resp]

    records = list(query_cdx("CC-MAIN-2025-51", "*.rw/*", cfg))
    assert len(records) == 2
    assert records[0].url == "https://igihe.com/article1"
    assert records[0].offset == 1000
    assert records[0].length == 5000
    assert records[0].crawl == "CC-MAIN-2025-51"
    assert records[1].url == "https://umuseke.rw/news"


@patch("apps.cc_index.cdx_client.requests.get")
def test_query_cdx_filters_status(mock_get):
    cfg = CCIndexConfig(
        cdx_page_size=1,
        cdx_rate_limit_s=0,
        status_filter=["200"],
    )

    num_pages_resp = MagicMock()
    num_pages_resp.text = "1"
    num_pages_resp.status_code = 200
    num_pages_resp.raise_for_status = MagicMock()

    # Mix 200 and 301 records
    lines = [
        json.dumps(
            {
                "url": "https://a.rw/ok",
                "filename": "f1",
                "offset": "0",
                "length": "100",
                "status": "200",
                "mime": "text/html",
            }
        ),
        json.dumps(
            {
                "url": "https://a.rw/redirect",
                "filename": "f2",
                "offset": "0",
                "length": "100",
                "status": "301",
                "mime": "text/html",
            }
        ),
    ]
    page_resp = MagicMock()
    page_resp.text = "\n".join(lines)
    page_resp.status_code = 200
    page_resp.raise_for_status = MagicMock()

    mock_get.side_effect = [num_pages_resp, page_resp]

    records = list(query_cdx("CC-MAIN-2025-51", "*.rw/*", cfg))
    assert len(records) == 1
    assert records[0].url == "https://a.rw/ok"


@patch("apps.cc_index.cdx_client.requests.get")
def test_query_cdx_json_num_pages(mock_get):
    """CDX API may return JSON for showNumPages instead of bare int."""
    cfg = CCIndexConfig(cdx_page_size=1, cdx_rate_limit_s=0)

    num_pages_resp = MagicMock()
    num_pages_resp.text = '{"pages": 1, "pageSize": 5, "blocks": 3}'
    num_pages_resp.status_code = 200
    num_pages_resp.raise_for_status = MagicMock()

    page_resp = MagicMock()
    page_resp.text = _cdx_ndjson_lines()
    page_resp.status_code = 200
    page_resp.raise_for_status = MagicMock()

    mock_get.side_effect = [num_pages_resp, page_resp]

    records = list(query_cdx("CC-MAIN-2025-51", "*.rw/*", cfg))
    assert len(records) == 2


@patch("apps.cc_index.cdx_client.requests.get")
def test_query_cdx_handles_zero_pages(mock_get):
    cfg = CCIndexConfig(cdx_page_size=5, cdx_rate_limit_s=0)

    resp = MagicMock()
    resp.text = '{"pages": 0, "pageSize": 5, "blocks": 0}'
    resp.status_code = 200
    resp.raise_for_status = MagicMock()
    mock_get.return_value = resp

    records = list(query_cdx("CC-MAIN-2025-51", "*.rw/*", cfg))
    assert records == []


@patch("apps.cc_index.cdx_client.requests.get")
def test_query_cdx_skips_malformed_lines(mock_get):
    cfg = CCIndexConfig(cdx_page_size=1, cdx_rate_limit_s=0)

    num_pages_resp = MagicMock()
    num_pages_resp.text = "1"
    num_pages_resp.status_code = 200
    num_pages_resp.raise_for_status = MagicMock()

    # One valid, one malformed JSON, one missing required fields
    lines = [
        json.dumps(
            {
                "url": "https://a.rw/ok",
                "filename": "f1",
                "offset": "0",
                "length": "100",
                "status": "200",
                "mime": "text/html",
            }
        ),
        "not valid json at all",
        json.dumps({"url": "https://a.rw/bad"}),  # missing filename, offset, length
    ]
    page_resp = MagicMock()
    page_resp.text = "\n".join(lines)
    page_resp.status_code = 200
    page_resp.raise_for_status = MagicMock()

    mock_get.side_effect = [num_pages_resp, page_resp]

    records = list(query_cdx("CC-MAIN-2025-51", "*.rw/*", cfg))
    assert len(records) == 1


@patch("apps.cc_index.cdx_client.query_cdx")
def test_build_record_list_deduplicates(mock_query):
    cfg = CCIndexConfig(
        domain_queries=["*.rw/*"],
        extra_domain_queries=[],
        cdx_rate_limit_s=0,
    )

    # Same URL+digest across two crawls → should keep only one
    rec1 = CDXRecord(
        url="https://a.rw/page",
        filename="f1",
        offset=0,
        length=100,
        status="200",
        mime="text/html",
        crawl="CC-MAIN-2025-51",
        digest="abc",
    )
    rec2 = CDXRecord(
        url="https://a.rw/page",
        filename="f2",
        offset=0,
        length=100,
        status="200",
        mime="text/html",
        crawl="CC-MAIN-2024-51",
        digest="abc",
    )
    rec3 = CDXRecord(
        url="https://b.rw/other",
        filename="f3",
        offset=0,
        length=200,
        status="200",
        mime="text/html",
        crawl="CC-MAIN-2025-51",
        digest="def",
    )

    mock_query.side_effect = [
        iter([rec1, rec3]),  # crawl 1
        iter([rec2]),  # crawl 2
    ]

    records = build_record_list(["CC-MAIN-2025-51", "CC-MAIN-2024-51"], cfg)
    assert len(records) == 2
    urls = {r.url for r in records}
    assert urls == {"https://a.rw/page", "https://b.rw/other"}

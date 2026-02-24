"""Tests for the Wayback Machine CDX API client."""

import json
from unittest.mock import MagicMock, patch

from apps.common.config_types import WaybackConfig
from apps.wayback.cdx_client import (
    WaybackRecord,
    build_wayback_record_list,
    query_wayback_cdx,
)


def _cfg(
    cdx_max_retries: int = 2,
    status_filter: list[str] | None = None,
    mime_filter: list[str] | None = None,
) -> WaybackConfig:
    return WaybackConfig(
        cdx_timeout_s=5,
        cdx_max_retries=cdx_max_retries,
        cdx_retry_backoff_s=0,
        cdx_rate_limit_s=0,
        from_year=2023,
        to_year=2024,
        status_filter=status_filter if status_filter is not None else ["200"],
        mime_filter=mime_filter if mime_filter is not None else ["text/html"],
    )


def _cdx_json_response():
    """Fake CDX JSON array response (first row is header)."""
    rows = [
        ["timestamp", "original", "statuscode", "mimetype", "length"],
        ["20231215120000", "https://igihe.com/article1", "200", "text/html", "5000"],
        ["20231210080000", "https://igihe.com/article2", "200", "text/html", "3000"],
    ]
    return json.dumps(rows)


@patch("apps.wayback.cdx_client.requests.get")
def test_query_wayback_cdx_parses_json(mock_get):
    cfg = _cfg()

    resp = MagicMock()
    resp.text = _cdx_json_response()
    resp.status_code = 200
    resp.raise_for_status = MagicMock()
    mock_get.return_value = resp

    records = list(query_wayback_cdx("igihe.com", cfg))
    assert len(records) == 2
    assert records[0].timestamp == "20231215120000"
    assert records[0].original_url == "https://igihe.com/article1"
    assert records[0].status_code == "200"
    assert records[0].mime_type == "text/html"
    assert records[0].length == 5000


@patch("apps.wayback.cdx_client.requests.get")
def test_query_wayback_cdx_sends_server_side_filters(mock_get):
    cfg = _cfg(status_filter=["200"], mime_filter=["text/html"])

    resp = MagicMock()
    resp.text = _cdx_json_response()
    resp.status_code = 200
    resp.raise_for_status = MagicMock()
    mock_get.return_value = resp

    list(query_wayback_cdx("igihe.com", cfg))

    # Verify server-side filter params were sent
    call_args = mock_get.call_args
    params = call_args.kwargs.get("params") or call_args[1].get("params")
    # params is a list of tuples
    filter_params = [v for k, v in params if k == "filter"]
    assert "statuscode:200" in filter_params
    assert "mimetype:text/html" in filter_params


@patch("apps.wayback.cdx_client.requests.get")
def test_query_wayback_cdx_handles_empty_response(mock_get):
    cfg = _cfg()

    resp = MagicMock()
    resp.text = "[]"
    resp.status_code = 200
    resp.raise_for_status = MagicMock()
    mock_get.return_value = resp

    records = list(query_wayback_cdx("empty.com", cfg))
    assert records == []


@patch("apps.wayback.cdx_client.requests.get")
def test_query_wayback_cdx_handles_rate_limit(mock_get):
    cfg = _cfg(cdx_max_retries=3)

    rate_limited = MagicMock()
    rate_limited.status_code = 429

    success = MagicMock()
    success.text = _cdx_json_response()
    success.status_code = 200
    success.raise_for_status = MagicMock()

    mock_get.side_effect = [rate_limited, success]

    records = list(query_wayback_cdx("igihe.com", cfg))
    assert len(records) == 2


@patch("apps.wayback.cdx_client.requests.get")
def test_query_wayback_cdx_skips_malformed_rows(mock_get):
    cfg = _cfg()

    rows = [
        ["timestamp", "original", "statuscode", "mimetype", "length"],
        ["20231215120000", "https://igihe.com/ok", "200", "text/html", "5000"],
        ["incomplete"],  # malformed: too few columns
    ]
    resp = MagicMock()
    resp.text = json.dumps(rows)
    resp.status_code = 200
    resp.raise_for_status = MagicMock()
    mock_get.return_value = resp

    records = list(query_wayback_cdx("igihe.com", cfg))
    assert len(records) == 1


def test_wayback_record_wayback_url():
    record = WaybackRecord(
        timestamp="20231215120000",
        original_url="https://igihe.com/article1",
        status_code="200",
        mime_type="text/html",
        length=5000,
    )
    expected = "https://web.archive.org/web/20231215120000id_/https://igihe.com/article1"
    assert record.wayback_url == expected


@patch("apps.wayback.cdx_client.query_wayback_cdx")
def test_build_wayback_record_list_predeups_by_latest(mock_query):
    cfg = _cfg()

    # Same URL with two timestamps — should keep the latest
    rec_old = WaybackRecord(
        timestamp="20230101000000",
        original_url="https://igihe.com/article1",
        status_code="200",
        mime_type="text/html",
        length=5000,
    )
    rec_new = WaybackRecord(
        timestamp="20231215120000",
        original_url="https://igihe.com/article1",
        status_code="200",
        mime_type="text/html",
        length=5500,
    )
    rec_other = WaybackRecord(
        timestamp="20231001000000",
        original_url="https://igihe.com/article2",
        status_code="200",
        mime_type="text/html",
        length=3000,
    )

    mock_query.return_value = iter([rec_old, rec_new, rec_other])

    records = build_wayback_record_list(["igihe.com"], cfg)
    assert len(records) == 2
    urls = {r.original_url for r in records}
    assert urls == {"https://igihe.com/article1", "https://igihe.com/article2"}

    # The article1 entry should be the newer one
    article1 = next(r for r in records if r.original_url == "https://igihe.com/article1")
    assert article1.timestamp == "20231215120000"


@patch("apps.wayback.cdx_client.query_wayback_cdx")
def test_build_wayback_record_list_multiple_domains(mock_query):
    cfg = _cfg()

    rec1 = WaybackRecord(
        timestamp="20231215120000",
        original_url="https://igihe.com/a",
        status_code="200",
        mime_type="text/html",
        length=1000,
    )
    rec2 = WaybackRecord(
        timestamp="20231215120000",
        original_url="https://umuseke.rw/b",
        status_code="200",
        mime_type="text/html",
        length=2000,
    )

    mock_query.side_effect = [iter([rec1]), iter([rec2])]

    records = build_wayback_record_list(["igihe.com", "umuseke.rw"], cfg)
    assert len(records) == 2

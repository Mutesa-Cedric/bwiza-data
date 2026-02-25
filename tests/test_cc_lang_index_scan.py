"""Tests for CC language-index scanner."""

import gzip
from unittest.mock import MagicMock, patch

from apps.cc_lang.index_scan import (
    LangIndexRecord,
    discover_crawl_ids,
    list_index_files,
    scan_crawl_for_language,
    scan_index_file,
)

# --- discover_crawl_ids ---


@patch("apps.cc_lang.index_scan.requests.get")
def test_discover_crawl_ids_filters_by_date(mock_get):
    mock_resp = MagicMock()
    mock_resp.json.return_value = [
        {"id": "CC-MAIN-2024-51"},
        {"id": "CC-MAIN-2020-10"},
        {"id": "CC-MAIN-2018-39"},
        {"id": "CC-MAIN-2017-04"},  # too old
        {"id": "CC-MAIN-2018-30"},  # too old (before 2018-39)
    ]
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    ids = discover_crawl_ids(min_date="2018-39")
    assert "CC-MAIN-2024-51" in ids
    assert "CC-MAIN-2020-10" in ids
    assert "CC-MAIN-2018-39" in ids
    assert "CC-MAIN-2017-04" not in ids
    assert "CC-MAIN-2018-30" not in ids


@patch("apps.cc_lang.index_scan.requests.get")
def test_discover_crawl_ids_max_crawls(mock_get):
    mock_resp = MagicMock()
    mock_resp.json.return_value = [{"id": f"CC-MAIN-2024-{i:02d}"} for i in range(1, 20)]
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    ids = discover_crawl_ids(max_crawls=5)
    assert len(ids) == 5
    # Should be sorted reverse (most recent first)
    assert ids[0] > ids[-1]


@patch("apps.cc_lang.index_scan.requests.get")
def test_discover_crawl_ids_max_date(mock_get):
    mock_resp = MagicMock()
    mock_resp.json.return_value = [
        {"id": "CC-MAIN-2024-51"},
        {"id": "CC-MAIN-2022-05"},
        {"id": "CC-MAIN-2020-10"},
    ]
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    ids = discover_crawl_ids(min_date="2018-39", max_date="2022-99")
    assert "CC-MAIN-2024-51" not in ids
    assert "CC-MAIN-2022-05" in ids
    assert "CC-MAIN-2020-10" in ids


@patch("apps.cc_lang.index_scan.requests.get")
def test_discover_crawl_ids_skips_non_main(mock_get):
    mock_resp = MagicMock()
    mock_resp.json.return_value = [
        {"id": "CC-MAIN-2024-51"},
        {"id": "CC-NEWS-2024-01"},  # not CC-MAIN
        {"id": "something-else"},
    ]
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    ids = discover_crawl_ids()
    assert ids == ["CC-MAIN-2024-51"]


# --- list_index_files ---


@patch("apps.cc_lang.index_scan.requests.get")
def test_list_index_files_from_paths_gz(mock_get):
    paths_content = "\n".join(
        [
            "cc-index/table/cc-main/warc/crawl=CC-MAIN-2024-51/subset=crawldiagnostics/part-00000.parquet",
            "cc-index/table/cc-main/warc/crawl=CC-MAIN-2024-51/subset=warc/part-00000-abc.gz.parquet",
            "cc-index/table/cc-main/warc/crawl=CC-MAIN-2024-51/subset=warc/part-00001-abc.gz.parquet",
            "cc-index/table/cc-main/warc/crawl=CC-MAIN-2024-51/subset=warc/_metadata",
        ]
    )
    mock_resp = MagicMock()
    mock_resp.content = gzip.compress(paths_content.encode())
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    keys = list_index_files("CC-MAIN-2024-51")
    assert len(keys) == 2
    assert all("subset=warc" in k for k in keys)
    assert all(k.endswith(".parquet") for k in keys)
    assert keys[0] < keys[1]  # sorted


@patch("apps.cc_lang.index_scan.requests.get")
def test_list_index_files_returns_empty_on_failure(mock_get):
    mock_get.side_effect = Exception("connection failed")
    keys = list_index_files("CC-MAIN-2024-51")
    assert keys == []


# --- scan_index_file ---


@patch("apps.cc_lang.index_scan.duckdb.connect")
def test_scan_index_file_returns_records(mock_connect):
    mock_con = MagicMock()
    mock_connect.return_value = mock_con
    mock_con.execute.return_value = mock_con
    mock_con.fetchall.return_value = [
        ("https://jw.org/kin/article1", "kin", "warc/file1.warc.gz", 1000, 5000),
        ("https://bible.com/kin/verse", "kin,eng", "warc/file2.warc.gz", 2000, 3000),
    ]

    records = scan_index_file("some/path/part-00000.parquet", lang_code="kin")
    assert len(records) == 2
    assert records[0].url == "https://jw.org/kin/article1"
    assert records[0].content_languages == "kin"
    assert records[0].warc_filename == "warc/file1.warc.gz"
    assert records[0].warc_record_offset == 1000
    assert records[0].warc_record_length == 5000
    assert records[1].content_languages == "kin,eng"


@patch("apps.cc_lang.index_scan.duckdb.connect")
def test_scan_index_file_no_matches(mock_connect):
    mock_con = MagicMock()
    mock_connect.return_value = mock_con
    mock_con.execute.return_value = mock_con
    mock_con.fetchall.return_value = []

    records = scan_index_file("some/path.parquet", lang_code="fra")
    assert len(records) == 0


@patch("apps.cc_lang.index_scan.duckdb.connect")
def test_scan_index_file_handles_error(mock_connect):
    mock_connect.side_effect = Exception("connection failed")
    records = scan_index_file("some/path.parquet", lang_code="kin")
    assert records == []


@patch("apps.cc_lang.index_scan.duckdb.connect")
def test_scan_index_file_handles_null_fields(mock_connect):
    mock_con = MagicMock()
    mock_connect.return_value = mock_con
    mock_con.execute.return_value = mock_con
    mock_con.fetchall.return_value = [
        (None, "kin", None, None, None),
    ]

    records = scan_index_file("some/path.parquet", lang_code="kin")
    assert len(records) == 1
    assert records[0].url == ""
    assert records[0].warc_filename == ""
    assert records[0].warc_record_offset == 0


# --- scan_crawl_for_language ---


@patch("apps.cc_lang.index_scan.time.sleep")
@patch("apps.cc_lang.index_scan.scan_index_file")
@patch("apps.cc_lang.index_scan.list_index_files")
def test_scan_crawl_for_language_yields_records(mock_list, mock_scan, mock_sleep):
    mock_list.return_value = ["file1.parquet", "file2.parquet"]

    rec1 = LangIndexRecord("https://a.com", "kin", "w1.warc.gz", 0, 100)
    rec2 = LangIndexRecord("https://b.com", "kin", "w2.warc.gz", 0, 200)
    mock_scan.side_effect = [[rec1], [rec2]]

    results = list(scan_crawl_for_language("CC-MAIN-2024-51", "kin", rate_limit_s=0))
    assert len(results) == 2
    assert results[0].url == "https://a.com"
    assert results[1].url == "https://b.com"


@patch("apps.cc_lang.index_scan.list_index_files")
def test_scan_crawl_empty_file_list(mock_list):
    mock_list.return_value = []
    results = list(scan_crawl_for_language("CC-MAIN-2024-51", "kin"))
    assert results == []


@patch("apps.cc_lang.index_scan.time.sleep")
@patch("apps.cc_lang.index_scan.scan_index_file")
@patch("apps.cc_lang.index_scan.list_index_files")
def test_scan_crawl_some_empty_files(mock_list, mock_scan, mock_sleep):
    """Files with no matches are silently skipped."""
    mock_list.return_value = ["f1.parquet", "f2.parquet", "f3.parquet"]
    rec = LangIndexRecord("https://x.com", "kin", "w.warc.gz", 0, 100)
    mock_scan.side_effect = [[], [rec], []]

    results = list(scan_crawl_for_language("CC-MAIN-2024-51", "kin", rate_limit_s=0))
    assert len(results) == 1
    assert results[0].url == "https://x.com"

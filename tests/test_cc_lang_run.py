"""Tests for the CC language-index mining runner."""

import gzip
import tempfile
from pathlib import Path
from unittest.mock import patch

from apps.cc_index.warc_fetch import WARCFetchResult
from apps.cc_lang.index_scan import LangIndexRecord
from apps.cc_lang.run import run_cc_lang_miner
from apps.common.config_types import AppConfig, CCIndexConfig, ShardingConfig

SAMPLE_HTML = (
    b"<html><body><main><p>"
    b"Mu Rwanda, uburezi ni ingenzi cyane ku iterambere ry'igihugu. "
    b"Abanyarwanda bose bagomba kubona uburezi bwiza kandi bukwiye. "
    b"Guverinoma y'u Rwanda yashyizeho politiki zitandukanye zo guteza "
    b"imbere uburezi mu gihugu hose. Ibi birimo gushyiraho amashuri "
    b"mashya no guteza imbere ikoranabuhanga mu burezi. "
    b"Umujyi wa Kigali ni umurwa mukuru wigihugu cyacu gikunda cyane. "
    b"Abantu bo mu turere dutandukanye bafite imico itandukanye koko. "
    b"Ubuhinzi bwigihugu bugomba guhindurwa kugirango butange umusaruro mwiza. "
    b"Inyamaswa zo mu mashyamba azwi muri Afurika zikurura abashakashatsi. "
    b"Imyidagaduro itandukanye irimo umupira no kwiruka bikunzwe neza."
    b"</p></main></body></html>"
)


def _make_warc_gz(url: str, html: bytes) -> bytes:
    http_response = b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n" + html
    warc_headers = (
        b"WARC/1.0\r\nWARC-Type: response\r\nWARC-Target-URI: " + url.encode() + b"\r\n\r\n"
    )
    return gzip.compress(warc_headers + http_response)


def _make_config(tmp_dir):
    return AppConfig(
        cc_index=CCIndexConfig(
            enabled=True,
            crawls=["CC-MAIN-2024-51"],
            discover_crawls=False,
            warc_concurrency=1,
            warc_max_retries=1,
            warc_retry_backoff_s=0,
            max_records=10,
        ),
        sharding=ShardingConfig(
            enabled=True,
            local_dir=str(tmp_dir / "shards"),
            target_compressed_mb=100,
        ),
    )


def _make_records(n: int) -> list[LangIndexRecord]:
    return [
        LangIndexRecord(
            url=f"https://site{i}.rw/page",
            content_languages="kin",
            warc_filename=f"warc/file{i}.warc.gz",
            warc_record_offset=i * 1000,
            warc_record_length=500,
        )
        for i in range(n)
    ]


@patch("apps.cc_lang.run.fetch_warc_record")
@patch("apps.cc_lang.run.scan_crawl_for_language")
@patch("apps.cc_lang.run.discover_crawl_ids")
@patch("apps.cc_miner.keep.predict_lang")
def test_runner_produces_stats(mock_lid, mock_discover, mock_scan, mock_fetch):
    mock_lid.return_value = ("kin_Latn", 0.95, "glotlid")
    mock_discover.return_value = ["CC-MAIN-2024-51"]
    records = _make_records(2)
    mock_scan.return_value = iter(records)

    def fake_fetch(filename, offset, length, cfg):
        idx = offset // 1000
        url = f"https://site{idx}.rw/page"
        unique_html = (
            b"<html><body><main><p>"
            b"Mu Rwanda uburezi ni ingenzi cyane ku iterambere igihugu. "
            b"Abanyarwanda bose bagomba kubona uburezi bwiza kandi bukwiye. "
            b"Guverinoma yashyizeho politiki zitandukanye zo guteza imbere. "
            b"Ibi birimo gushyiraho amashuri mashya no ikoranabuhanga. "
            b"Umujyi wa Kigali ni umurwa mukuru wigihugu cyacu gikunda. "
            b"Abantu bo mu turere dutandukanye bafite imico itandukanye. "
            b"Ubuhinzi bwigihugu bugomba guhindurwa kugirango butange umusaruro. "
            b"Inyamaswa zo mu mashyamba azwi muri Afurika zikurura benshi. "
            + url.encode()
            + b"</p></main></body></html>"
        )
        return WARCFetchResult(raw_data=_make_warc_gz(url, unique_html))

    mock_fetch.side_effect = fake_fetch

    with tempfile.TemporaryDirectory() as d:
        cfg = _make_config(Path(d))
        stats = run_cc_lang_miner(cfg, lang_code="kin", max_crawls=1)

    assert stats.docs_seen == 2
    assert stats.docs_kept == 2


@patch("apps.cc_lang.run.fetch_warc_record")
@patch("apps.cc_lang.run.scan_crawl_for_language")
@patch("apps.cc_lang.run.discover_crawl_ids")
@patch("apps.cc_miner.keep.predict_lang")
def test_runner_handles_fetch_errors(mock_lid, mock_discover, mock_scan, mock_fetch):
    mock_lid.return_value = ("kin_Latn", 0.95, "glotlid")
    mock_discover.return_value = ["CC-MAIN-2024-51"]
    mock_scan.return_value = iter(_make_records(2))
    mock_fetch.return_value = WARCFetchResult(ok=False, error="connection_error")

    with tempfile.TemporaryDirectory() as d:
        cfg = _make_config(Path(d))
        stats = run_cc_lang_miner(cfg, lang_code="kin", max_crawls=1)

    assert stats.docs_seen == 2
    assert stats.docs_kept == 0
    assert stats.reject_reasons["reject.warc_fetch.connection_error"] == 2


@patch("apps.cc_lang.run.fetch_warc_record")
@patch("apps.cc_lang.run.scan_crawl_for_language")
@patch("apps.cc_lang.run.discover_crawl_ids")
def test_runner_handles_bad_warc(mock_discover, mock_scan, mock_fetch):
    mock_discover.return_value = ["CC-MAIN-2024-51"]
    mock_scan.return_value = iter(_make_records(1))
    mock_fetch.return_value = WARCFetchResult(raw_data=b"not gzip at all")

    with tempfile.TemporaryDirectory() as d:
        cfg = _make_config(Path(d))
        stats = run_cc_lang_miner(cfg, lang_code="kin", max_crawls=1)

    assert stats.docs_seen == 1
    assert stats.docs_kept == 0
    assert any("warc_parse" in k for k in stats.reject_reasons)


@patch("apps.cc_lang.run.scan_crawl_for_language")
@patch("apps.cc_lang.run.discover_crawl_ids")
def test_runner_empty_scan(mock_discover, mock_scan):
    mock_discover.return_value = ["CC-MAIN-2024-51"]
    mock_scan.return_value = iter([])

    with tempfile.TemporaryDirectory() as d:
        cfg = _make_config(Path(d))
        stats = run_cc_lang_miner(cfg, lang_code="kin", max_crawls=1)

    assert stats.docs_seen == 0
    assert stats.docs_kept == 0


@patch("apps.cc_lang.run.scan_crawl_for_language")
@patch("apps.cc_lang.run.discover_crawl_ids")
def test_runner_no_crawls(mock_discover, mock_scan):
    mock_discover.return_value = []

    with tempfile.TemporaryDirectory() as d:
        cfg = _make_config(Path(d))
        stats = run_cc_lang_miner(cfg, lang_code="kin", max_crawls=1)

    assert stats.docs_seen == 0
    mock_scan.assert_not_called()


@patch("apps.cc_lang.run.fetch_warc_record")
@patch("apps.cc_lang.run.scan_crawl_for_language")
@patch("apps.cc_lang.run.discover_crawl_ids")
@patch("apps.cc_miner.keep.predict_lang")
def test_runner_domain_stats(mock_lid, mock_discover, mock_scan, mock_fetch):
    mock_lid.return_value = ("kin_Latn", 0.95, "glotlid")
    mock_discover.return_value = ["CC-MAIN-2024-51"]
    mock_scan.return_value = iter(_make_records(1))

    def fake_fetch(filename, offset, length, cfg):
        return WARCFetchResult(raw_data=_make_warc_gz("https://site0.rw/page", SAMPLE_HTML))

    mock_fetch.side_effect = fake_fetch

    with tempfile.TemporaryDirectory() as d:
        cfg = _make_config(Path(d))
        stats = run_cc_lang_miner(cfg, lang_code="kin", max_crawls=1)

    assert stats.domain_seen["site0.rw"] == 1
    assert stats.domain_kept["site0.rw"] == 1

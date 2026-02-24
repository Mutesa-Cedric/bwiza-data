"""Tests for the Wayback Machine mining runner."""

import tempfile
from pathlib import Path
from unittest.mock import patch

from apps.common.config_types import AppConfig, ShardingConfig, WaybackConfig
from apps.wayback.cdx_client import WaybackRecord
from apps.wayback.fetch import WaybackFetchResult
from apps.wayback.run import run_wayback_miner

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


def _make_config(tmp_dir: Path) -> AppConfig:
    return AppConfig(
        wayback=WaybackConfig(
            enabled=True,
            domains=["igihe.com"],
            from_year=2023,
            to_year=2024,
            fetch_concurrency=1,
            fetch_max_retries=1,
            fetch_retry_backoff_s=0,
            cdx_rate_limit_s=0,
            fetch_rate_limit_s=0,
            max_records=10,
        ),
        sharding=ShardingConfig(
            enabled=True,
            local_dir=str(tmp_dir / "shards"),
            target_compressed_mb=100,
        ),
    )


def _make_records(n: int) -> list[WaybackRecord]:
    return [
        WaybackRecord(
            timestamp=f"2023121512{i:04d}",
            original_url=f"https://igihe.com/article{i}",
            status_code="200",
            mime_type="text/html",
            length=5000,
        )
        for i in range(n)
    ]


@patch("apps.wayback.run.build_wayback_record_list")
@patch("apps.wayback.run.fetch_wayback_page")
@patch("apps.cc_miner.keep.predict_lang")
def test_wayback_runner_produces_stats(mock_lid, mock_fetch, mock_cdx):
    mock_lid.return_value = ("kin_Latn", 0.95, "glotlid")
    mock_cdx.return_value = _make_records(3)
    mock_fetch.return_value = WaybackFetchResult(html_bytes=SAMPLE_HTML)

    with tempfile.TemporaryDirectory() as d:
        cfg = _make_config(Path(d))
        stats = run_wayback_miner(cfg)

    assert stats.docs_seen == 3


@patch("apps.wayback.run.build_wayback_record_list")
@patch("apps.wayback.run.fetch_wayback_page")
@patch("apps.cc_miner.keep.predict_lang")
def test_wayback_runner_keeps_rw_docs(mock_lid, mock_fetch, mock_cdx):
    mock_lid.return_value = ("kin_Latn", 0.95, "glotlid")
    mock_cdx.return_value = _make_records(2)
    mock_fetch.return_value = WaybackFetchResult(html_bytes=SAMPLE_HTML)

    with tempfile.TemporaryDirectory() as d:
        cfg = _make_config(Path(d))
        stats = run_wayback_miner(cfg)

    # All same content → only first kept, rest deduped
    assert stats.docs_kept >= 1


@patch("apps.wayback.run.build_wayback_record_list")
@patch("apps.wayback.run.fetch_wayback_page")
def test_wayback_runner_handles_fetch_errors(mock_fetch, mock_cdx):
    mock_cdx.return_value = _make_records(2)
    mock_fetch.return_value = WaybackFetchResult(ok=False, error="timeout")

    with tempfile.TemporaryDirectory() as d:
        cfg = _make_config(Path(d))
        stats = run_wayback_miner(cfg)

    assert stats.docs_seen == 2
    assert stats.docs_kept == 0
    assert "reject.wayback_fetch.timeout" in stats.reject_reasons


@patch("apps.wayback.run.build_wayback_record_list")
def test_wayback_runner_empty_records(mock_cdx):
    mock_cdx.return_value = []

    with tempfile.TemporaryDirectory() as d:
        cfg = _make_config(Path(d))
        stats = run_wayback_miner(cfg)

    assert stats.docs_seen == 0
    assert stats.docs_kept == 0


@patch("apps.wayback.run.build_wayback_record_list")
@patch("apps.wayback.run.fetch_wayback_page")
@patch("apps.cc_miner.keep.predict_lang")
def test_wayback_runner_dedup_across_timestamps(mock_lid, mock_fetch, mock_cdx):
    mock_lid.return_value = ("kin_Latn", 0.95, "glotlid")
    # Two records with different timestamps but same content (SAMPLE_HTML)
    mock_cdx.return_value = [
        WaybackRecord(
            timestamp="20231201000000",
            original_url="https://igihe.com/article1",
            status_code="200",
            mime_type="text/html",
            length=5000,
        ),
        WaybackRecord(
            timestamp="20231215120000",
            original_url="https://igihe.com/article1",
            status_code="200",
            mime_type="text/html",
            length=5000,
        ),
    ]
    mock_fetch.return_value = WaybackFetchResult(html_bytes=SAMPLE_HTML)

    with tempfile.TemporaryDirectory() as d:
        cfg = _make_config(Path(d))
        stats = run_wayback_miner(cfg)

    assert stats.docs_seen == 2
    assert stats.docs_kept == 1
    assert stats.duplicates == 1

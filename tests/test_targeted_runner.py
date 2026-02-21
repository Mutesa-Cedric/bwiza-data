"""Tests for the targeted crawler end-to-end runner."""

import tempfile
from pathlib import Path
from unittest.mock import patch

from apps.common.config_types import AppConfig, ShardingConfig, TargetedConfig
from apps.targeted_crawler.fetch import FetchResult
from apps.targeted_crawler.run import run_targeted_crawler

SAMPLE_HTML = b"""
<html>
<head><title>Test Kinyarwanda Page</title></head>
<body>
<main>
<p>Mu Rwanda, uburezi ni ingenzi cyane ku iterambere ry'igihugu.
Abanyarwanda bose bagomba kubona uburezi bwiza kandi bukwiye.
Guverinoma y'u Rwanda yashyizeho politiki zitandukanye zo guteza
imbere uburezi mu gihugu hose. Ibi birimo gushyiraho amashuri
mashya no guteza imbere ikoranabuhanga mu burezi.
Mu Rwanda, uburezi ni ingenzi cyane ku iterambere ry'igihugu.
Abanyarwanda bose bagomba kubona uburezi bwiza kandi bukwiye.</p>
</main>
<a href="/page2">More</a>
</body>
</html>
"""


def _make_config(tmp_dir, seeds_file):
    return AppConfig(
        targeted=TargetedConfig(
            enabled=True,
            seeds_file=str(seeds_file),
            max_pages=3,
            per_domain_max_pages=3,
            concurrency=1,
            request_timeout_s=5,
            max_retries=1,
            retry_backoff_s=0,
            crawl_delay_s=0,
            obey_robots_txt=False,
        ),
        sharding=ShardingConfig(
            enabled=True,
            local_dir=str(tmp_dir / "shards"),
            target_compressed_mb=100,
        ),
    )


@patch("apps.targeted_crawler.run.fetch_url")
@patch("apps.cc_miner.keep.predict_lang")
def test_runner_produces_stats(mock_lid, mock_fetch):
    mock_lid.return_value = ("kin_Latn", 0.95, "glotlid")
    mock_fetch.return_value = FetchResult(
        url="https://example.rw/",
        status_code=200,
        content_type="text/html",
        content=SAMPLE_HTML,
        final_url="https://example.rw/",
    )

    with tempfile.TemporaryDirectory() as d:
        tmp_dir = Path(d)
        seeds_file = tmp_dir / "seeds.txt"
        seeds_file.write_text("example.rw\n")
        cfg = _make_config(tmp_dir, seeds_file)
        stats = run_targeted_crawler(cfg)

    assert stats.docs_seen > 0


@patch("apps.targeted_crawler.run.fetch_url")
@patch("apps.cc_miner.keep.predict_lang")
def test_runner_keeps_rw_docs(mock_lid, mock_fetch):
    mock_lid.return_value = ("kin_Latn", 0.95, "glotlid")
    mock_fetch.return_value = FetchResult(
        url="https://example.rw/",
        status_code=200,
        content_type="text/html",
        content=SAMPLE_HTML,
        final_url="https://example.rw/",
    )

    with tempfile.TemporaryDirectory() as d:
        tmp_dir = Path(d)
        seeds_file = tmp_dir / "seeds.txt"
        seeds_file.write_text("example.rw\n")
        cfg = _make_config(tmp_dir, seeds_file)
        stats = run_targeted_crawler(cfg)

    assert stats.docs_kept >= 1


@patch("apps.targeted_crawler.run.fetch_url")
def test_runner_handles_fetch_errors(mock_fetch):
    mock_fetch.return_value = FetchResult(
        url="https://example.rw/",
        error="connection_error",
    )

    with tempfile.TemporaryDirectory() as d:
        tmp_dir = Path(d)
        seeds_file = tmp_dir / "seeds.txt"
        seeds_file.write_text("example.rw\n")
        cfg = _make_config(tmp_dir, seeds_file)
        stats = run_targeted_crawler(cfg)

    assert stats.docs_kept == 0
    assert stats.docs_seen > 0


def test_runner_empty_seeds():
    with tempfile.TemporaryDirectory() as d:
        tmp_dir = Path(d)
        seeds_file = tmp_dir / "seeds.txt"
        seeds_file.write_text("# only comments\n")
        cfg = _make_config(tmp_dir, seeds_file)
        stats = run_targeted_crawler(cfg)

    assert stats.docs_seen == 0
    assert stats.docs_kept == 0

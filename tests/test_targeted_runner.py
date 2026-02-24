"""Tests for the targeted crawler end-to-end runner."""

import tempfile
import time
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


@patch("apps.targeted_crawler.run.fetch_url")
@patch("apps.cc_miner.keep.predict_lang")
def test_runner_concurrent_fetching(mock_lid, mock_fetch):
    """Run with concurrency=4, multiple domains, verify all pages processed."""
    mock_lid.return_value = ("kin_Latn", 0.95, "glotlid")

    call_times: list[float] = []

    def fake_fetch(url, cfg):
        call_times.append(time.monotonic())
        # Embed URL in content so each page is unique (avoids dedup)
        unique_html = (
            b"<html><body><main><p>Mu Rwanda uburezi ni ingenzi cyane "
            b"ku iterambere igihugu. Abanyarwanda bose bagomba kubona "
            b"uburezi bwiza kandi bukwiye guverinoma. "
            + url.encode()
            + b"</p></main></body></html>"
        )
        return FetchResult(
            url=url,
            status_code=200,
            content_type="text/html",
            content=unique_html,
            final_url=url,
        )

    mock_fetch.side_effect = fake_fetch

    with tempfile.TemporaryDirectory() as d:
        tmp_dir = Path(d)
        seeds_file = tmp_dir / "seeds.txt"
        # 4 different domains so rate limiter doesn't serialize them
        seeds_file.write_text("a.rw\nb.rw\nc.rw\nd.rw\n")
        cfg = AppConfig(
            targeted=TargetedConfig(
                enabled=True,
                seeds_file=str(seeds_file),
                max_pages=4,
                per_domain_max_pages=1,
                concurrency=4,
                request_timeout_s=5,
                max_retries=1,
                retry_backoff_s=0,
                crawl_delay_s=0,
                obey_robots_txt=False,
                min_lid_confidence=0.85,
            ),
            sharding=ShardingConfig(
                enabled=True,
                local_dir=str(tmp_dir / "shards"),
                target_compressed_mb=100,
            ),
        )
        stats = run_targeted_crawler(cfg)

    # All 4 seeds should be fetched and processed
    assert stats.docs_seen == 4
    assert stats.docs_kept == 4
    assert len(call_times) == 4

    # With concurrency=4 and crawl_delay_s=0, all 4 fetches should
    # happen nearly simultaneously (within 1 second of each other)
    span = max(call_times) - min(call_times)
    assert span < 2.0, f"Expected concurrent fetches, but span was {span:.2f}s"


@patch("apps.targeted_crawler.run.fetch_url")
@patch("apps.cc_miner.keep.predict_lang")
def test_runner_domain_stats(mock_lid, mock_fetch):
    """Per-domain stats are tracked in RunStats."""
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

    assert stats.domain_seen["example.rw"] >= 1
    assert stats.domain_kept["example.rw"] >= 1
    d = stats.to_dict()
    assert "domain_stats" in d
    assert "example.rw" in d["domain_stats"]

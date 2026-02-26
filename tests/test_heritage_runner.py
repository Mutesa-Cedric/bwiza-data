"""Tests for heritage end-to-end runner."""

import tempfile
from pathlib import Path
from unittest.mock import patch

from apps.common.config_types import AppConfig, HeritageConfig, ShardingConfig
from apps.heritage.run import run_heritage
from apps.targeted_crawler.fetch import FetchResult

LISTING_HTML = b"""
<html><body>
<a href="/news-details/inteko-yumuco">Inteko</a>
<a href="/news-details/umuganura">Umuganura</a>
</body></html>
"""

ARTICLE_HTML = b"""
<html><body><main>
<h1>Inteko y'Umuco</h1>
<p>Mu Rwanda uburezi ni ingenzi cyane ku iterambere ry'igihugu.
Abanyeshuri biga amasomo atandukanye harimo ikinyarwanda n'ubumenyi rusange.
Igitabo cyiza gifasha umunyeshuri gusobanukirwa neza no gukora imyitozo.
Muri gahunda y'uburezi, abarimu n'ababyeyi bafatanya gutera imbere no gutsinda.
Iyi nyandiko irimo amagambo menshi ahagije kugira ngo irenge imipaka y'iyungurura.</p>
</main></body></html>
"""


def _make_config(tmp_dir: Path) -> AppConfig:
    return AppConfig(
        heritage=HeritageConfig(
            enabled=True,
            seed_listing_urls=["https://rwandaheritage.gov.rw/amakuru"],
            allowed_domain="rwandaheritage.gov.rw",
            max_listing_pages=2,
            concurrency=1,
            request_timeout_s=5,
            max_retries=1,
            retry_backoff_s=0,
            domain_delay_s=0,
            max_response_bytes=5_000_000,
            output_source="heritage_gov_rw",
            min_lid_confidence=0.85,
            extract_mode="precision",
        ),
        sharding=ShardingConfig(
            enabled=True,
            local_dir=str(tmp_dir / "shards"),
            target_compressed_mb=100,
        ),
    )


@patch("apps.heritage.harvest.fetch_url")
@patch("apps.heritage.discovery.fetch_url")
@patch("apps.cc_miner.keep.predict_lang")
def test_heritage_runner_keeps_rw_docs(mock_lid, mock_discovery_fetch, mock_harvest_fetch):
    mock_lid.return_value = ("kin_Latn", 0.95, "glotlid")

    # Discovery phase: return listing with links
    mock_discovery_fetch.return_value = FetchResult(
        url="https://rwandaheritage.gov.rw/amakuru",
        status_code=200,
        content_type="text/html",
        content=LISTING_HTML,
        final_url="https://rwandaheritage.gov.rw/amakuru",
    )

    # Harvest phase: return article content
    mock_harvest_fetch.return_value = FetchResult(
        url="https://rwandaheritage.gov.rw/news-details/inteko-yumuco",
        status_code=200,
        content_type="text/html",
        content=ARTICLE_HTML,
        final_url="https://rwandaheritage.gov.rw/news-details/inteko-yumuco",
    )

    with tempfile.TemporaryDirectory() as d:
        tmp_dir = Path(d)
        cfg = _make_config(tmp_dir)
        stats = run_heritage(cfg)

    assert stats.docs_seen >= 1
    assert stats.docs_kept >= 1


@patch("apps.heritage.harvest.fetch_url")
@patch("apps.heritage.discovery.fetch_url")
def test_heritage_runner_handles_harvest_errors(mock_discovery_fetch, mock_harvest_fetch):
    # Discovery finds pages
    mock_discovery_fetch.return_value = FetchResult(
        url="https://rwandaheritage.gov.rw/amakuru",
        status_code=200,
        content_type="text/html",
        content=LISTING_HTML,
        final_url="https://rwandaheritage.gov.rw/amakuru",
    )

    # Harvest fails
    mock_harvest_fetch.return_value = FetchResult(
        url="https://rwandaheritage.gov.rw/news-details/inteko-yumuco",
        error="timeout",
    )

    with tempfile.TemporaryDirectory() as d:
        tmp_dir = Path(d)
        cfg = _make_config(tmp_dir)
        stats = run_heritage(cfg)

    assert stats.docs_seen >= 1
    assert stats.docs_kept == 0


@patch("apps.heritage.discovery.fetch_url")
def test_heritage_runner_empty_discovery(mock_discovery_fetch):
    """Runner should complete gracefully when discovery finds nothing."""
    mock_discovery_fetch.return_value = FetchResult(
        url="https://rwandaheritage.gov.rw/amakuru",
        error="connection_error",
    )

    with tempfile.TemporaryDirectory() as d:
        tmp_dir = Path(d)
        cfg = _make_config(tmp_dir)
        stats = run_heritage(cfg)

    assert stats.docs_seen == 0
    assert stats.docs_kept == 0


@patch("apps.heritage.discovery.fetch_url")
def test_heritage_runner_dry_run(mock_discovery_fetch):
    """Dry-run should only run discovery, not harvest."""
    mock_discovery_fetch.return_value = FetchResult(
        url="https://rwandaheritage.gov.rw/amakuru",
        status_code=200,
        content_type="text/html",
        content=LISTING_HTML,
        final_url="https://rwandaheritage.gov.rw/amakuru",
    )

    with tempfile.TemporaryDirectory() as d:
        tmp_dir = Path(d)
        cfg = _make_config(tmp_dir)
        stats = run_heritage(cfg, dry_run=True)

    # Discovery ran but no harvest
    assert stats.docs_seen == 0
    assert stats.docs_kept == 0

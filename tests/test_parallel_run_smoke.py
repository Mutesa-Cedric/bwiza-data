"""Smoke tests for parallel corpus runner (mocked, offline)."""

import tempfile
from pathlib import Path
from unittest.mock import patch

from apps.common.config_types import AppConfig, ParallelConfig, ShardingConfig
from apps.parallel_corpus.run import run_parallel_corpus
from apps.targeted_crawler.fetch import FetchResult

# Page with hreflang links pointing to rw and en versions
BILINGUAL_PAGE = b"""
<html>
<head>
<link rel="alternate" hreflang="rw" href="/rw/article" />
<link rel="alternate" hreflang="en" href="/en/article" />
</head>
<body><p>Some content</p></body>
</html>
"""

RW_PAGE = b"""
<html><body><main>
<p>Mu Rwanda, uburezi ni ingenzi cyane ku iterambere ry'igihugu.
Abanyarwanda bose bagomba kubona uburezi bwiza kandi bukwiye.
Guverinoma yashyizeho politiki zo guteza imbere uburezi hose.</p>
</main></body></html>
"""

EN_PAGE = b"""
<html><body><main>
<p>In Rwanda, education is very important for the country's development.
All Rwandans must have access to quality and appropriate education.
The government has put in place policies to promote education.</p>
</main></body></html>
"""


def _make_config(tmp_dir, seeds_file):
    return AppConfig(
        parallel=ParallelConfig(
            enabled=True,
            seeds_file=str(seeds_file),
            max_pages=5,
            per_domain_max_pages=5,
            request_timeout_s=5,
            max_retries=1,
            retry_backoff_s=0,
            crawl_delay_s=0,
            obey_robots_txt=False,
            min_chars=50,
            min_lid_conf=0.8,
        ),
        sharding=ShardingConfig(
            enabled=True,
            local_dir=str(tmp_dir / "shards"),
            target_compressed_mb=100,
        ),
    )


@patch("apps.parallel_corpus.run.fetch_url")
@patch("apps.common.lid.predict_lang")
def test_runner_finds_pairs(mock_lid, mock_fetch):
    mock_lid.side_effect = lambda text: (
        ("kin_Latn", 0.92, "glotlid")
        if "uburezi" in text.lower()
        else ("eng_Latn", 0.95, "glotlid")
    )

    def side_effect(url, cfg):
        if "/rw/" in url:
            return FetchResult(
                url=url,
                status_code=200,
                content_type="text/html",
                content=RW_PAGE,
                final_url=url,
            )
        elif "/en/" in url:
            return FetchResult(
                url=url,
                status_code=200,
                content_type="text/html",
                content=EN_PAGE,
                final_url=url,
            )
        else:
            return FetchResult(
                url=url,
                status_code=200,
                content_type="text/html",
                content=BILINGUAL_PAGE,
                final_url=url,
            )

    mock_fetch.side_effect = side_effect

    with tempfile.TemporaryDirectory() as d:
        tmp_dir = Path(d)
        seeds_file = tmp_dir / "seeds.txt"
        seeds_file.write_text("example.rw\n")
        cfg = _make_config(tmp_dir, seeds_file)
        stats = run_parallel_corpus(cfg)

    assert stats.docs_seen >= 1
    assert stats.docs_kept >= 1


@patch("apps.parallel_corpus.run.fetch_url")
def test_runner_handles_no_pairs(mock_fetch):
    mock_fetch.return_value = FetchResult(
        url="https://example.rw/",
        status_code=200,
        content_type="text/html",
        content=b"<html><body>No language links</body></html>",
        final_url="https://example.rw/",
    )

    with tempfile.TemporaryDirectory() as d:
        tmp_dir = Path(d)
        seeds_file = tmp_dir / "seeds.txt"
        seeds_file.write_text("example.rw\n")
        cfg = _make_config(tmp_dir, seeds_file)
        stats = run_parallel_corpus(cfg)

    assert stats.docs_kept == 0


def test_runner_empty_seeds():
    with tempfile.TemporaryDirectory() as d:
        tmp_dir = Path(d)
        seeds_file = tmp_dir / "seeds.txt"
        seeds_file.write_text("# empty\n")
        cfg = _make_config(tmp_dir, seeds_file)
        stats = run_parallel_corpus(cfg)

    assert stats.docs_seen == 0

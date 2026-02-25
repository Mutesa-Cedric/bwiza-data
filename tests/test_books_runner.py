"""Tests for books corpus runner."""

import tempfile
from pathlib import Path
from unittest.mock import patch

from apps.books_corpus.run import run_books_corpus
from apps.common.config_types import AppConfig, BooksConfig, ShardingConfig
from apps.targeted_crawler.fetch import FetchResult

SAMPLE_HTML = b"""
<html><body><main>
<p>Mu Rwanda uburezi ni ingenzi cyane ku iterambere ry'igihugu.
Abanyeshuri biga amasomo atandukanye harimo ikinyarwanda n'ubumenyi rusange.
Igitabo cyiza gifasha umunyeshuri gusobanukirwa neza no gukora imyitozo.
Muri gahunda y'uburezi, abarimu n'ababyeyi bafatanya gutera imbere no gutsinda.
Iyi nyandiko irimo amagambo menshi ahagije kugira ngo irenge imipaka y'iyungurura.</p>
</main></body></html>
"""


def _make_config(tmp_dir: Path, seeds_file: Path) -> AppConfig:
    return AppConfig(
        books=BooksConfig(
            enabled=True,
            seeds_file=str(seeds_file),
            concurrency=2,
            request_timeout_s=5,
            max_retries=1,
            retry_backoff_s=0,
            domain_delay_s=0,
            max_response_bytes=5_000_000,
            output_source="books_corpus",
            min_lid_confidence=0.85,
            extract_mode="precision",
        ),
        sharding=ShardingConfig(
            enabled=True,
            local_dir=str(tmp_dir / "shards"),
            target_compressed_mb=100,
        ),
    )


@patch("apps.books_corpus.run.fetch_url")
@patch("apps.cc_miner.keep.predict_lang")
def test_books_runner_keeps_rw_docs(mock_lid, mock_fetch):
    mock_lid.return_value = ("kin_Latn", 0.95, "glotlid")
    mock_fetch.return_value = FetchResult(
        url="https://example.org/book.html",
        status_code=200,
        content_type="text/html",
        content=SAMPLE_HTML,
        final_url="https://example.org/book.html",
    )

    with tempfile.TemporaryDirectory() as d:
        tmp_dir = Path(d)
        seeds_file = tmp_dir / "books.txt"
        seeds_file.write_text("https://example.org/book.html\n", encoding="utf-8")
        cfg = _make_config(tmp_dir, seeds_file)
        stats = run_books_corpus(cfg)

    assert stats.docs_seen == 1
    assert stats.docs_kept == 1


@patch("apps.books_corpus.run.fetch_url")
def test_books_runner_handles_fetch_errors(mock_fetch):
    mock_fetch.return_value = FetchResult(url="https://example.org/book.html", error="timeout")

    with tempfile.TemporaryDirectory() as d:
        tmp_dir = Path(d)
        seeds_file = tmp_dir / "books.txt"
        seeds_file.write_text("https://example.org/book.html\n", encoding="utf-8")
        cfg = _make_config(tmp_dir, seeds_file)
        stats = run_books_corpus(cfg)

    assert stats.docs_seen == 1
    assert stats.docs_kept == 0


def test_books_runner_empty_seeds_file():
    with tempfile.TemporaryDirectory() as d:
        tmp_dir = Path(d)
        seeds_file = tmp_dir / "books.txt"
        seeds_file.write_text("# none\n", encoding="utf-8")
        cfg = _make_config(tmp_dir, seeds_file)
        stats = run_books_corpus(cfg)

    assert stats.docs_seen == 0
    assert stats.docs_kept == 0

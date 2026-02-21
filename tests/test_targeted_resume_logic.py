"""Tests for targeted crawler resumable execution logic."""

import tempfile
from pathlib import Path
from unittest.mock import patch

from apps.common.config_types import AppConfig, ShardingConfig, TargetedConfig
from apps.common.run_state import RunState
from apps.targeted_crawler.fetch import FetchResult
from apps.targeted_crawler.run import run_targeted_crawler


def _make_config(tmp_dir, seeds_file):
    return AppConfig(
        targeted=TargetedConfig(
            enabled=True,
            seeds_file=str(seeds_file),
            max_pages=5,
            per_domain_max_pages=5,
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
@patch("apps.targeted_crawler.run.save_state")
@patch("apps.targeted_crawler.run.load_state", return_value=None)
@patch("apps.targeted_crawler.run.load_done_set", return_value=set())
@patch("apps.targeted_crawler.run.mark_done")
def test_new_run_creates_state(mock_mark_done, mock_done_set, mock_load, mock_save, mock_fetch):
    mock_fetch.return_value = FetchResult(
        url="https://example.rw/",
        status_code=200,
        content_type="text/html",
        content=b"<html><body>Simple page</body></html>",
        final_url="https://example.rw/",
    )

    with tempfile.TemporaryDirectory() as d:
        tmp_dir = Path(d)
        seeds_file = tmp_dir / "seeds.txt"
        seeds_file.write_text("example.rw\n")
        cfg = _make_config(tmp_dir, seeds_file)

        run_targeted_crawler(cfg)

    assert mock_save.call_count >= 2
    final_state = mock_save.call_args_list[-1][0][0]
    assert final_state.pipeline == "targeted_crawler"
    assert final_state.source == "targeted_web"


@patch("apps.targeted_crawler.run.fetch_url")
@patch("apps.targeted_crawler.run.save_state")
@patch("apps.targeted_crawler.run.mark_done")
def test_resume_skips_done_urls(mock_mark_done, mock_save, mock_fetch):
    mock_fetch.return_value = FetchResult(
        url="https://example.rw/page2",
        status_code=200,
        content_type="text/html",
        content=b"<html><body>Page two</body></html>",
        final_url="https://example.rw/page2",
    )

    state = RunState(
        run_id="existing_run",
        pipeline="targeted_crawler",
        source="targeted_web",
        status="paused",
    )

    with tempfile.TemporaryDirectory() as d:
        tmp_dir = Path(d)
        seeds_file = tmp_dir / "seeds.txt"
        seeds_file.write_text("example.rw\n")
        cfg = _make_config(tmp_dir, seeds_file)

        with (
            patch(
                "apps.targeted_crawler.run.load_state",
                return_value=state,
            ),
            patch(
                "apps.targeted_crawler.run.load_done_set",
                return_value={"https://example.rw/"},
            ),
        ):
            run_targeted_crawler(cfg, resume_run_id="existing_run")

    # The seed URL https://example.rw/ should have been marked
    # as fetched in the frontier, so only new discovered URLs
    # would be fetched. With no new links, fetch should not be
    # called for the already-done seed.
    for call in mock_fetch.call_args_list:
        assert call[0][0] != "https://example.rw/"


@patch("apps.targeted_crawler.run.fetch_url")
@patch("apps.targeted_crawler.run.save_state")
@patch("apps.targeted_crawler.run.load_state", return_value=None)
@patch("apps.targeted_crawler.run.load_done_set", return_value=set())
@patch("apps.targeted_crawler.run.mark_done")
def test_completes_on_success(mock_mark_done, mock_done_set, mock_load, mock_save, mock_fetch):
    mock_fetch.return_value = FetchResult(
        url="https://example.rw/",
        status_code=200,
        content_type="text/html",
        content=b"<html><body>Simple page</body></html>",
        final_url="https://example.rw/",
    )

    with tempfile.TemporaryDirectory() as d:
        tmp_dir = Path(d)
        seeds_file = tmp_dir / "seeds.txt"
        seeds_file.write_text("example.rw\n")
        cfg = _make_config(tmp_dir, seeds_file)

        run_targeted_crawler(cfg)

    final_state = mock_save.call_args_list[-1][0][0]
    assert final_state.status == "completed"


def test_empty_seeds_no_state():
    with tempfile.TemporaryDirectory() as d:
        tmp_dir = Path(d)
        seeds_file = tmp_dir / "seeds.txt"
        seeds_file.write_text("# empty\n")
        cfg = _make_config(tmp_dir, seeds_file)

        stats = run_targeted_crawler(cfg)

    assert stats.docs_seen == 0

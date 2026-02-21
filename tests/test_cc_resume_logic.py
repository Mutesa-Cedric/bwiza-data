"""Tests for CC miner resumable execution logic."""

import tempfile
from pathlib import Path
from unittest.mock import patch

from apps.cc_miner.run_many import run_cc_miner
from apps.common.config_types import AppConfig, CCConfig, OutputConfig, ShardingConfig
from apps.common.run_state import RunState


def _make_config(tmp_dir, wet_file):
    return AppConfig(
        cc=CCConfig(
            wet_paths_file=str(wet_file),
            max_wet_files=10,
        ),
        output=OutputConfig(
            local_dir=str(tmp_dir / "outputs"),
        ),
        sharding=ShardingConfig(
            enabled=True,
            local_dir=str(tmp_dir / "shards"),
            target_compressed_mb=100,
        ),
    )


def _write_wet_paths(tmp_dir, urls):
    wet_file = tmp_dir / "wet_paths.txt"
    wet_file.write_text("\n".join(urls) + "\n")
    return wet_file


@patch("apps.cc_miner.run_many.run_one_wet")
@patch("apps.cc_miner.run_many.save_state")
@patch("apps.cc_miner.run_many.load_state", return_value=None)
@patch("apps.cc_miner.run_many.load_done_set", return_value=set())
@patch("apps.cc_miner.run_many.mark_done")
def test_new_run_creates_state(mock_mark_done, mock_done_set, mock_load, mock_save, mock_run_one):
    with tempfile.TemporaryDirectory() as d:
        tmp_dir = Path(d)
        wet_file = _write_wet_paths(tmp_dir, ["https://example.com/wet1"])
        cfg = _make_config(tmp_dir, wet_file)

        run_cc_miner(cfg)

    # save_state called multiple times (start, after wet, complete, finally)
    assert mock_save.call_count >= 2
    # The state object is passed by reference and mutated; check final state
    final_state = mock_save.call_args_list[-1][0][0]
    assert final_state.pipeline == "cc_miner"
    assert final_state.source == "commoncrawl"
    assert final_state.run_id != ""


@patch("apps.cc_miner.run_many.run_one_wet")
@patch("apps.cc_miner.run_many.save_state")
@patch("apps.cc_miner.run_many.mark_done")
def test_resume_skips_done_wets(mock_mark_done, mock_save, mock_run_one):
    with tempfile.TemporaryDirectory() as d:
        tmp_dir = Path(d)
        wet_file = _write_wet_paths(
            tmp_dir,
            ["https://example.com/wet1", "https://example.com/wet2"],
        )
        cfg = _make_config(tmp_dir, wet_file)

        # Create existing state
        state = RunState(
            run_id="existing_run",
            pipeline="cc_miner",
            source="commoncrawl",
            status="paused",
            items_done=1,
        )

        with (
            patch(
                "apps.cc_miner.run_many.load_state",
                return_value=state,
            ),
            patch(
                "apps.cc_miner.run_many.load_done_set",
                return_value={"https://example.com/wet1"},
            ),
        ):
            run_cc_miner(cfg, resume_run_id="existing_run")

    # Only wet2 should be processed (wet1 skipped)
    assert mock_run_one.call_count == 1
    call_url = mock_run_one.call_args[0][0]
    assert call_url == "https://example.com/wet2"


@patch("apps.cc_miner.run_many.run_one_wet")
@patch("apps.cc_miner.run_many.save_state")
@patch("apps.cc_miner.run_many.load_state", return_value=None)
@patch("apps.cc_miner.run_many.load_done_set", return_value=set())
@patch("apps.cc_miner.run_many.mark_done")
def test_marks_done_after_success(
    mock_mark_done, mock_done_set, mock_load, mock_save, mock_run_one
):
    with tempfile.TemporaryDirectory() as d:
        tmp_dir = Path(d)
        wet_file = _write_wet_paths(tmp_dir, ["https://example.com/wet1"])
        cfg = _make_config(tmp_dir, wet_file)

        run_cc_miner(cfg)

    mock_mark_done.assert_called_once()
    assert "wet1" in mock_mark_done.call_args[0][1]


@patch("apps.cc_miner.run_many.run_one_wet", side_effect=Exception("boom"))
@patch("apps.cc_miner.run_many.save_state")
@patch("apps.cc_miner.run_many.load_state", return_value=None)
@patch("apps.cc_miner.run_many.load_done_set", return_value=set())
@patch("apps.cc_miner.run_many.mark_done")
def test_failed_wet_not_marked_done(
    mock_mark_done, mock_done_set, mock_load, mock_save, mock_run_one
):
    with tempfile.TemporaryDirectory() as d:
        tmp_dir = Path(d)
        wet_file = _write_wet_paths(tmp_dir, ["https://example.com/wet1"])
        cfg = _make_config(tmp_dir, wet_file)

        run_cc_miner(cfg)

    # Should NOT be marked done if it failed
    mock_mark_done.assert_not_called()


@patch("apps.cc_miner.run_many.run_one_wet")
@patch("apps.cc_miner.run_many.save_state")
@patch("apps.cc_miner.run_many.load_state", return_value=None)
@patch("apps.cc_miner.run_many.load_done_set", return_value=set())
@patch("apps.cc_miner.run_many.mark_done")
def test_completes_on_success(mock_mark_done, mock_done_set, mock_load, mock_save, mock_run_one):
    with tempfile.TemporaryDirectory() as d:
        tmp_dir = Path(d)
        wet_file = _write_wet_paths(tmp_dir, ["https://example.com/wet1"])
        cfg = _make_config(tmp_dir, wet_file)

        run_cc_miner(cfg)

    # Last save should have completed status
    final_state = mock_save.call_args_list[-1][0][0]
    assert final_state.status == "completed"

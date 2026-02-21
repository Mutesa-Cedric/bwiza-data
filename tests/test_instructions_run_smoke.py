"""Smoke tests for instruction dataset runner (offline)."""

import json
import tempfile
from pathlib import Path

from apps.common.config_types import (
    AppConfig,
    InstructionsConfig,
    ShardingConfig,
)
from apps.instructions.run import run_instructions


def _make_config(tmp_dir, seed_file):
    return AppConfig(
        instructions=InstructionsConfig(
            enabled=True,
            seed_file=str(seed_file),
            target_count=100,
            min_chars_prompt=2,
            min_chars_response=2,
        ),
        sharding=ShardingConfig(
            enabled=True,
            local_dir=str(tmp_dir / "shards"),
            target_compressed_mb=100,
        ),
    )


def test_runner_with_gold_seeds():
    with tempfile.TemporaryDirectory() as d:
        tmp_dir = Path(d)
        seed_file = tmp_dir / "seeds.jsonl"
        seeds = [
            {
                "prompt": "Kigali ni iki?",
                "response": "Kigali ni umurwa mukuru w'u Rwanda.",
                "task_type": "qa",
            },
            {
                "prompt": "Rwanda iri he?",
                "response": "Rwanda riri mu burasirazuba bw'Afurika.",
                "task_type": "qa",
            },
        ]
        seed_file.write_text("\n".join(json.dumps(s) for s in seeds))

        cfg = _make_config(tmp_dir, seed_file)
        stats = run_instructions(cfg)

    assert stats.docs_kept >= 2
    assert stats.docs_seen >= 2


def test_runner_no_seeds_synthetic_only():
    with tempfile.TemporaryDirectory() as d:
        tmp_dir = Path(d)
        seed_file = tmp_dir / "empty.jsonl"
        seed_file.write_text("")

        cfg = _make_config(tmp_dir, seed_file)
        stats = run_instructions(cfg)

    # Synthetic examples have empty responses, so all get rejected
    assert stats.docs_seen > 0
    assert stats.docs_kept == 0


def test_runner_dedup():
    with tempfile.TemporaryDirectory() as d:
        tmp_dir = Path(d)
        seed_file = tmp_dir / "seeds.jsonl"
        # Same example twice
        seed = {
            "prompt": "Kigali ni iki?",
            "response": "Umurwa mukuru.",
        }
        seed_file.write_text(json.dumps(seed) + "\n" + json.dumps(seed))

        cfg = _make_config(tmp_dir, seed_file)
        stats = run_instructions(cfg)

    assert stats.docs_kept == 1
    assert stats.duplicates == 1


def test_runner_respects_target_count():
    with tempfile.TemporaryDirectory() as d:
        tmp_dir = Path(d)
        seed_file = tmp_dir / "seeds.jsonl"
        seeds = [
            {
                "prompt": f"Ikibazo {i}?",
                "response": f"Igisubizo {i}.",
            }
            for i in range(10)
        ]
        seed_file.write_text("\n".join(json.dumps(s) for s in seeds))

        cfg = AppConfig(
            instructions=InstructionsConfig(
                enabled=True,
                seed_file=str(seed_file),
                target_count=3,
                min_chars_prompt=2,
                min_chars_response=2,
            ),
            sharding=ShardingConfig(
                enabled=True,
                local_dir=str(tmp_dir / "shards"),
                target_compressed_mb=100,
            ),
        )
        stats = run_instructions(cfg)

    assert stats.docs_kept == 3

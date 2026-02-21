"""Aggregate dataset-level statistics from index entries."""

import json
from collections import defaultdict
from pathlib import Path

from apps.common.dataset_index import read_index
from apps.common.logging import get_logger

log = get_logger(__name__)


def build_stats(index_path: str) -> dict:
    """Build aggregate statistics from an index file."""
    entries = read_index(index_path)

    per_source: dict[str, dict[str, int]] = defaultdict(
        lambda: {"shards": 0, "bytes": 0, "records": 0, "tokens": 0}
    )
    per_run: dict[str, dict[str, int]] = defaultdict(
        lambda: {"shards": 0, "bytes": 0, "records": 0, "tokens": 0}
    )

    total_shards = 0
    total_bytes = 0
    total_records = 0
    total_tokens = 0

    for entry in entries:
        total_shards += 1
        total_bytes += entry.bytes
        total_records += entry.records
        total_tokens += entry.token_estimate

        src = per_source[entry.source]
        src["shards"] += 1
        src["bytes"] += entry.bytes
        src["records"] += entry.records
        src["tokens"] += entry.token_estimate

        run = per_run[entry.run_id]
        run["shards"] += 1
        run["bytes"] += entry.bytes
        run["records"] += entry.records
        run["tokens"] += entry.token_estimate

    stats = {
        "total_shards": total_shards,
        "total_bytes": total_bytes,
        "total_records": total_records,
        "total_token_estimate": total_tokens,
        "per_source": dict(per_source),
        "per_run": dict(per_run),
    }

    log.info(
        "Stats: shards=%d records=%d tokens=%d bytes=%d",
        total_shards,
        total_records,
        total_tokens,
        total_bytes,
    )
    return stats


def build_and_write_stats(index_path: str, output_path: str | Path) -> Path:
    """Build stats and write to a JSON file."""
    stats = build_stats(index_path)
    p = Path(output_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)
    log.info("Wrote stats to %s", p)
    return p

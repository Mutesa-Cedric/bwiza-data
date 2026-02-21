"""Minimal dataset metadata generator."""

import json
from datetime import datetime, timezone
from pathlib import Path

from apps.common.dataset_index import read_index
from apps.common.logging import get_logger

log = get_logger(__name__)


def build_metadata(
    dataset: str,
    version: str,
    index_path: str,
    config_fingerprints: list[str] | None = None,
) -> dict:
    """Build minimal dataset metadata from an index file."""
    entries = read_index(index_path)

    sources = sorted({e.source for e in entries})
    total_shards = len(entries)
    total_records = sum(e.records for e in entries)
    total_tokens = sum(e.token_estimate for e in entries)

    return {
        "name": f"bwiza-{dataset}",
        "version": version,
        "dataset_type": dataset,
        "build_time": datetime.now(timezone.utc).isoformat(),
        "sources": sources,
        "total_shards": total_shards,
        "total_records": total_records,
        "total_token_estimate": total_tokens,
        "config_fingerprints": config_fingerprints or [],
        "license_note": "Internal use only. See project documentation for licensing details.",
        "intended_use": "Training and evaluation of Kinyarwanda language models.",
    }


def build_and_write_metadata(
    dataset: str,
    version: str,
    index_path: str,
    output_path: str | Path,
    config_fingerprints: list[str] | None = None,
) -> Path:
    """Build metadata and write to JSON file."""
    meta = build_metadata(dataset, version, index_path, config_fingerprints)
    p = Path(output_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
    log.info("Wrote dataset metadata to %s", p)
    return p

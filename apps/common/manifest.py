"""Append-only shard manifest writer."""

import json
from dataclasses import asdict
from pathlib import Path

from apps.common.logging import get_logger
from apps.common.shard_writer import ShardMeta

log = get_logger(__name__)


def manifest_path(run_id: str, base_dir: str = "manifests/shards") -> Path:
    """Return the manifest file path for a run."""
    p = Path(base_dir)
    p.mkdir(parents=True, exist_ok=True)
    return p / f"{run_id}.jsonl"


def append_manifest_entry(
    run_id: str, entry: ShardMeta, source: str = "", base_dir: str = "manifests/shards"
) -> None:
    """Append a shard entry to the run manifest."""
    path = manifest_path(run_id, base_dir)
    record = {
        "run_id": run_id,
        "source": source,
        **asdict(entry),
    }
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    log.info("Manifest entry appended: %s -> %s", entry.filename, path)


def read_manifest(run_id: str, base_dir: str = "manifests/shards") -> list[dict]:
    """Read all entries from a run manifest."""
    path = manifest_path(run_id, base_dir)
    if not path.exists():
        return []
    entries = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries

"""Dataset index schema for training-ready dataset packaging."""

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from apps.common.logging import get_logger

log = get_logger(__name__)

# Map pipeline source names to dataset types
SOURCE_TO_DATASET: dict[str, str] = {
    "commoncrawl": "pretrain",
    "targeted_web": "pretrain",
    "wikipedia": "pretrain",
    "mbazanlp_v01.1": "pretrain",
    "kinnews": "pretrain",
    "parallel_web": "parallel",
    "instructions_rw": "instructions",
}

VALID_DATASETS = {"pretrain", "parallel", "instructions"}


def dataset_for_source(source: str) -> str:
    """Return the dataset type for a given source name.

    Raises ValueError if source is unknown.
    """
    ds = SOURCE_TO_DATASET.get(source)
    if ds is None:
        raise ValueError(f"Unknown source: {source!r}")
    return ds


@dataclass
class DatasetIndexEntry:
    """A single entry in a dataset index, representing one shard."""

    dataset: str
    version: str
    run_id: str
    source: str
    shard_name: str
    s3_bucket: str
    s3_key: str
    bytes: int
    records: int
    token_estimate: int
    checksum_sha256: str
    created_at: str
    meta: dict = field(default_factory=dict)

    def to_json(self) -> dict:
        return asdict(self)

    @classmethod
    def from_json(cls, data: dict) -> "DatasetIndexEntry":
        known = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)


def write_index(entries: list[DatasetIndexEntry], path: str | Path) -> Path:
    """Write index entries to a JSONL file."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry.to_json(), ensure_ascii=False) + "\n")
    log.info("Wrote %d index entries to %s", len(entries), p)
    return p


def read_index(path: str | Path) -> list[DatasetIndexEntry]:
    """Read index entries from a JSONL file."""
    p = Path(path)
    if not p.exists():
        return []
    entries = []
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(DatasetIndexEntry.from_json(json.loads(line)))
    return entries

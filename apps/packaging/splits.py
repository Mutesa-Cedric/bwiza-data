"""Deterministic dataset split generator."""

import hashlib
from pathlib import Path

from apps.common.dataset_index import read_index
from apps.common.logging import get_logger

log = get_logger(__name__)

DEFAULT_SEED = "bwiza-v1-stable"
DEFAULT_RATIOS = (0.98, 0.01, 0.01)  # train, val, test


def _assign_split(s3_key: str, seed: str, ratios: tuple[float, float, float]) -> str:
    """Assign an entry to a split based on stable hash."""
    h = hashlib.sha256(f"{seed}:{s3_key}".encode()).hexdigest()
    bucket = int(h[:8], 16) % 10000

    train_upper = int(ratios[0] * 10000)
    val_upper = train_upper + int(ratios[1] * 10000)

    if bucket < train_upper:
        return "train"
    elif bucket < val_upper:
        return "val"
    else:
        return "test"


def build_splits(
    index_path: str,
    seed: str = DEFAULT_SEED,
    ratios: tuple[float, float, float] = DEFAULT_RATIOS,
) -> dict[str, list[str]]:
    """Build train/val/test splits from an index file.

    Returns dict mapping split name to list of S3 keys.
    """
    entries = read_index(index_path)
    splits: dict[str, list[str]] = {"train": [], "val": [], "test": []}

    for entry in entries:
        split = _assign_split(entry.s3_key, seed, ratios)
        splits[split].append(entry.s3_key)

    for name, keys in splits.items():
        keys.sort()

    log.info(
        "Splits: train=%d val=%d test=%d",
        len(splits["train"]),
        len(splits["val"]),
        len(splits["test"]),
    )
    return splits


def write_splits(splits: dict[str, list[str]], output_dir: str | Path) -> Path:
    """Write split files (train.txt, val.txt, test.txt)."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    for name, keys in splits.items():
        path = out / f"{name}.txt"
        with open(path, "w", encoding="utf-8") as f:
            for key in keys:
                f.write(key + "\n")

    log.info("Wrote splits to %s", out)
    return out


def build_and_write_splits(
    index_path: str,
    output_dir: str,
    seed: str = DEFAULT_SEED,
    ratios: tuple[float, float, float] = DEFAULT_RATIOS,
) -> Path:
    """Build splits and write to disk."""
    splits = build_splits(index_path, seed, ratios)
    return write_splits(splits, output_dir)


def build_mixed_splits_and_write(
    index_path: str,
    output_dir: str,
    enrichment_path: str | None = None,
    mix_config_path: str | None = None,
) -> Path:
    """Build content-type-aware mixed splits and write to disk."""
    from apps.packaging.mixing import MixConfig, build_mixed_splits

    config = MixConfig.from_json(mix_config_path) if mix_config_path else None
    splits = build_mixed_splits(index_path, enrichment_path, config)
    return write_splits(splits, output_dir)

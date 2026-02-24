"""Config-driven data mixing by content_type for balanced splits."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from apps.common.dataset_index import DatasetIndexEntry, read_index
from apps.common.logging import get_logger
from apps.packaging.enrich import (
    EnrichedMeta,
    classify_content_type,
    read_enrichment_index,
)
from apps.packaging.splits import _assign_split

log = get_logger(__name__)

DEFAULT_MIX_RATIOS: dict[str, float] = {
    "news": 0.30,
    "government": 0.25,
    "wiki": 0.15,
    "religious": 0.10,
    "external_dataset": 0.10,
    "academic": 0.05,
    "other": 0.05,
}


@dataclass
class MixConfig:
    """Configuration for data mixing."""

    ratios: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_MIX_RATIOS))
    seed: str = "bwiza-v1-stable"
    split_ratios: tuple[float, float, float] = (0.98, 0.01, 0.01)

    def validate(self) -> None:
        """Raise ValueError if ratios don't approximately sum to 1.0."""
        total = sum(self.ratios.values())
        if abs(total - 1.0) > 0.01:
            raise ValueError(f"Mix ratios sum to {total:.4f}, expected ~1.0")
        for name, ratio in self.ratios.items():
            if ratio < 0:
                raise ValueError(f"Negative ratio for {name}: {ratio}")

    @classmethod
    def from_json(cls, path: str | Path) -> MixConfig:
        """Load config from a JSON file."""
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        ratios = data.get("ratios", dict(DEFAULT_MIX_RATIOS))
        seed = data.get("seed", "bwiza-v1-stable")
        split_ratios = tuple(data.get("split_ratios", [0.98, 0.01, 0.01]))
        return cls(ratios=ratios, seed=seed, split_ratios=split_ratios)

    def to_json(self) -> dict:
        return {
            "ratios": self.ratios,
            "seed": self.seed,
            "split_ratios": list(self.split_ratios),
        }


def classify_shard_content_type(
    entry: DatasetIndexEntry,
    enrichment: dict[str, EnrichedMeta] | None = None,
) -> str:
    """Determine the content_type for a shard.

    Each shard is single-source, so we classify based on the source field.
    If enrichment data is available, use the majority content_type from docs.
    Otherwise fall back to classify_content_type(source, domain_from_source).
    """
    if enrichment:
        # Find docs belonging to this shard
        shard_types: dict[str, int] = defaultdict(int)
        for meta in enrichment.values():
            if meta.shard_name == entry.shard_name:
                shard_types[meta.content_type] += 1
        if shard_types:
            return max(shard_types, key=shard_types.get)  # type: ignore[arg-type]

    # Fallback: classify from source alone (domain unknown at shard level)
    return classify_content_type(entry.source, "")


def _deterministic_shuffle(items: list, seed: str) -> list:
    """Deterministic shuffle using seeded hashing."""
    return sorted(items, key=lambda x: hashlib.sha256(f"{seed}:{x.s3_key}".encode()).hexdigest())


def build_mixed_splits(
    index_path: str,
    enrichment_path: str | None = None,
    config: MixConfig | None = None,
) -> dict[str, list[str]]:
    """Build train/val/test splits with content-type-aware mixing.

    Algorithm:
    1. Read index entries, group shards by content_type.
    2. Compute available tokens per content_type.
    3. Compute target tokens per content_type from ratios.
    4. Under-represented types: take all shards, redistribute surplus.
    5. Over-represented types: sample proportionally to fill target.
    6. Assign selected shards to train/val/test via _assign_split.

    Returns:
        dict mapping split name to sorted list of S3 keys.
    """
    if config is None:
        config = MixConfig()
    config.validate()

    entries = read_index(index_path)
    if not entries:
        return {"train": [], "val": [], "test": []}

    # Load enrichment data if available
    enrichment = None
    if enrichment_path:
        enrichment = read_enrichment_index(enrichment_path)

    # Group shards by content_type
    groups: dict[str, list[DatasetIndexEntry]] = defaultdict(list)
    for entry in entries:
        ct = classify_shard_content_type(entry, enrichment)
        groups[ct].append(entry)

    # Compute total available tokens across all groups
    total_tokens = sum(e.token_estimate for e in entries)
    if total_tokens == 0:
        # Fallback: use record count as proxy
        total_tokens = sum(e.records for e in entries)

    # Phase 1: Identify under- and over-represented types
    selected: list[DatasetIndexEntry] = []
    surplus_ratio = 0.0

    under_represented: set[str] = set()
    for ct, ratio in config.ratios.items():
        group = groups.get(ct, [])
        available = sum(e.token_estimate for e in group)
        target = total_tokens * ratio
        if available <= target:
            under_represented.add(ct)

    # Phase 2: Take all from under-represented, compute leftover
    for ct in under_represented:
        group = groups.get(ct, [])
        selected.extend(group)
        available = sum(e.token_estimate for e in group)
        target = total_tokens * config.ratios.get(ct, 0)
        if target > 0 and available < target:
            surplus_ratio += config.ratios[ct] - (available / total_tokens if total_tokens else 0)

    # Phase 3: For over-represented types, sample to fill target (+ redistributed surplus)
    over_types = [ct for ct in config.ratios if ct not in under_represented]
    over_total_ratio = sum(config.ratios[ct] for ct in over_types)

    for ct in over_types:
        group = groups.get(ct, [])
        if not group:
            continue

        base_ratio = config.ratios[ct]
        # Redistribute surplus proportionally
        if over_total_ratio > 0:
            extra = surplus_ratio * (base_ratio / over_total_ratio)
        else:
            extra = 0
        effective_ratio = base_ratio + extra

        target_tokens = total_tokens * effective_ratio
        available_tokens = sum(e.token_estimate for e in group)

        if available_tokens <= target_tokens:
            selected.extend(group)
        else:
            # Deterministic shuffle, take enough to fill target
            shuffled = _deterministic_shuffle(group, config.seed)
            running = 0
            for entry in shuffled:
                selected.append(entry)
                running += entry.token_estimate
                if running >= target_tokens:
                    break

    # Also include any shards from content_types not in config.ratios
    known_types = set(config.ratios.keys()) | under_represented
    for ct, group in groups.items():
        if ct not in known_types:
            selected.extend(group)

    # Assign to train/val/test splits
    splits: dict[str, list[str]] = {"train": [], "val": [], "test": []}
    for entry in selected:
        split = _assign_split(entry.s3_key, config.seed, config.split_ratios)
        splits[split].append(entry.s3_key)

    for keys in splits.values():
        keys.sort()

    log.info(
        "Mixed splits: train=%d val=%d test=%d (from %d shards, %d content types)",
        len(splits["train"]),
        len(splits["val"]),
        len(splits["test"]),
        len(selected),
        len(groups),
    )
    return splits

"""Deterministic shard naming convention."""


def shard_name(prefix: str, source: str, run_id: str, part: int) -> str:
    """Generate a deterministic shard filename."""
    return f"{prefix}_{source}_{run_id}_part-{part:06d}.jsonl.zst"

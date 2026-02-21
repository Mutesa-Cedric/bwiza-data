"""Deterministic S3 key builders for shards, manifests, and stats."""


def _join(prefix: str, *parts: str) -> str:
    """Join prefix and parts with '/', stripping trailing slashes from prefix."""
    return "/".join([prefix.rstrip("/")] + list(parts))


def shard_key(prefix: str, run_id: str, filename: str) -> str:
    """S3 key for a shard file: <prefix>/shards/run_id=<run_id>/<filename>"""
    return _join(prefix, "shards", f"run_id={run_id}", filename)


def manifest_key(prefix: str, run_id: str) -> str:
    """S3 key for a manifest: <prefix>/manifests/run_id=<run_id>.jsonl"""
    return _join(prefix, "manifests", f"run_id={run_id}.jsonl")


def stats_key(prefix: str, run_id: str) -> str:
    """S3 key for a stats file: <prefix>/stats/run_id=<run_id>.json"""
    return _join(prefix, "stats", f"run_id={run_id}.json")

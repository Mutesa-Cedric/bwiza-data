#!/usr/bin/env python3
"""List S3 contents for a run: shards, manifest, stats."""

import sys

from apps.common.config import load_config
from apps.common.s3_client import get_s3_client
from apps.common.s3_paths import manifest_key, stats_key


def _head_exists(client, bucket, key):
    """Check if an object exists and return its size, or None."""
    from botocore.exceptions import ClientError

    try:
        resp = client.head_object(Bucket=bucket, Key=key)
        return resp["ContentLength"]
    except ClientError:
        return None


def main() -> int:
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <run_id> [config_path]", file=sys.stderr)
        return 1

    run_id = sys.argv[1]
    config_path = sys.argv[2] if len(sys.argv) > 2 else "configs/default.yaml"

    cfg = load_config(config_path)
    if not cfg.s3.enabled:
        print("S3 is not enabled in config.", file=sys.stderr)
        return 1

    client = get_s3_client(cfg.s3)
    bucket = cfg.s3.bucket
    prefix = cfg.s3.prefix.rstrip("/")
    shard_prefix = f"{prefix}/shards/run_id={run_id}/"

    # List shards
    paginator = client.get_paginator("list_objects_v2")
    shard_count = 0
    shard_bytes = 0

    for page in paginator.paginate(Bucket=bucket, Prefix=shard_prefix):
        for obj in page.get("Contents", []):
            shard_count += 1
            shard_bytes += obj["Size"]
            print(f"  shard: {obj['Key']} ({obj['Size']} bytes)")

    # Check manifest
    mk = manifest_key(cfg.s3.prefix, run_id)
    manifest_size = _head_exists(client, bucket, mk)

    # Check stats
    sk = stats_key(cfg.s3.prefix, run_id)
    stats_size = _head_exists(client, bucket, sk)

    print(f"\n--- Run {run_id} on s3://{bucket}/{prefix}/ ---")
    print(f"  Shards: {shard_count} ({shard_bytes} bytes)")
    print(f"  Manifest: {'present' if manifest_size else 'MISSING'}", end="")
    if manifest_size:
        print(f" ({manifest_size} bytes)")
    else:
        print()
    print(f"  Stats: {'present' if stats_size else 'MISSING'}", end="")
    if stats_size:
        print(f" ({stats_size} bytes)")
    else:
        print()

    if shard_count == 0:
        print("\n  WARNING: No shards found for this run.")

    return 0


if __name__ == "__main__":
    sys.exit(main())

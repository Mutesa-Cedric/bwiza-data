#!/usr/bin/env python3
"""Upload a completed run to S3."""

import sys

from apps.cc_miner.upload_run import upload_run
from apps.common.config import load_config


def main() -> int:
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <run_id> [config_path]", file=sys.stderr)
        return 1

    run_id = sys.argv[1]
    config_path = sys.argv[2] if len(sys.argv) > 2 else "configs/default.yaml"

    cfg = load_config(config_path)
    if not cfg.s3.enabled:
        print("S3 is not enabled in config. Set s3.enabled: true.", file=sys.stderr)
        return 1

    summary = upload_run(cfg, run_id)

    print(f"\nUpload summary for run_id={run_id}:")
    print(f"  Uploaded: {summary['uploaded']}")
    print(f"  Skipped: {summary['skipped']}")
    print(f"  Total bytes: {summary['total_bytes']}")

    if summary["errors"]:
        print(f"  Errors: {len(summary['errors'])}")
        for err in summary["errors"]:
            print(f"    - {err}")
        return 1

    print("  Status: ALL OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())

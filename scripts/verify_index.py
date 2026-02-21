#!/usr/bin/env python3
"""Verify a dataset index against S3 objects."""

import argparse
import sys

from apps.common.config import load_config
from apps.common.s3_client import get_s3_client
from apps.packaging.verify_index import verify_index


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify dataset index against S3")
    parser.add_argument("--index", required=True, help="Path to index.jsonl")
    parser.add_argument("--bucket", required=True, help="S3 bucket name")
    args = parser.parse_args()

    cfg = load_config()
    client = get_s3_client(cfg.s3)

    result = verify_index(args.index, client, args.bucket)

    print(f"Total: {result.total}")
    print(f"OK: {result.ok}")
    print(f"Missing: {result.missing}")
    print(f"Size mismatch: {result.size_mismatch}")

    if result.errors:
        print("\nErrors:")
        for err in result.errors:
            print(f"  {err}")

    return 0 if result.passed else 1


if __name__ == "__main__":
    sys.exit(main())

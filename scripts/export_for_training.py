#!/usr/bin/env python3
"""Export training-ready file lists as S3 URIs.

Reads a split file (e.g. splits/train.txt) and prints S3 URIs
that can be consumed directly by a training script.
"""

import argparse
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Export split as S3 URIs for training")
    parser.add_argument("--split-file", required=True, help="Path to split file (e.g. train.txt)")
    parser.add_argument("--bucket", required=True, help="S3 bucket name")
    args = parser.parse_args()

    path = Path(args.split_file)
    if not path.exists():
        print(f"Error: split file not found: {path}", file=sys.stderr)
        return 1

    for line in path.read_text().strip().splitlines():
        key = line.strip()
        if key:
            print(f"s3://{args.bucket}/{key}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

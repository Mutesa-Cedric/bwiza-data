#!/usr/bin/env python3
"""Generate deterministic train/val/test splits from a dataset index."""

import argparse
import sys

from apps.packaging.splits import build_and_write_splits


def main() -> int:
    parser = argparse.ArgumentParser(description="Build dataset splits")
    parser.add_argument("--index", required=True, help="Path to index.jsonl")
    parser.add_argument("--output-dir", required=True, help="Output directory for split files")
    parser.add_argument("--seed", default="bwiza-v1-stable", help="Hash seed for split stability")
    args = parser.parse_args()

    path = build_and_write_splits(args.index, args.output_dir, seed=args.seed)
    print(f"Splits written to: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

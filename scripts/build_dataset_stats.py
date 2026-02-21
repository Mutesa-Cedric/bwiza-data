#!/usr/bin/env python3
"""Build aggregate statistics for a dataset from its index."""

import argparse
import sys

from apps.packaging.dataset_stats import build_and_write_stats


def main() -> int:
    parser = argparse.ArgumentParser(description="Build dataset statistics")
    parser.add_argument("--index", required=True, help="Path to index.jsonl")
    parser.add_argument("--output", required=True, help="Output path for stats.json")
    args = parser.parse_args()

    path = build_and_write_stats(args.index, args.output)
    print(f"Stats written to: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

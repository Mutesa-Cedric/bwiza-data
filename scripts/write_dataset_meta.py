#!/usr/bin/env python3
"""Generate minimal dataset metadata."""

import argparse
import sys

from apps.packaging.dataset_meta import build_and_write_metadata


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate dataset metadata")
    parser.add_argument("--dataset", required=True, help="Dataset type")
    parser.add_argument("--version", default="v1", help="Dataset version")
    parser.add_argument("--index", required=True, help="Path to index.jsonl")
    parser.add_argument("--output", required=True, help="Output path for dataset_meta.json")
    args = parser.parse_args()

    path = build_and_write_metadata(args.dataset, args.version, args.index, args.output)
    print(f"Metadata written to: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

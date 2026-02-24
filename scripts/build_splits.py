#!/usr/bin/env python3
"""Generate deterministic train/val/test splits from a dataset index."""

import argparse
import sys

from apps.common.logging import setup_logging
from apps.packaging.splits import build_and_write_splits, build_mixed_splits_and_write


def main() -> int:
    parser = argparse.ArgumentParser(description="Build dataset splits")
    parser.add_argument("--index", required=True, help="Path to index.jsonl")
    parser.add_argument("--output-dir", required=True, help="Output directory for split files")
    parser.add_argument("--seed", default="bwiza-v1-stable", help="Hash seed for split stability")
    parser.add_argument(
        "--enrichment",
        default=None,
        help="Path to enrichment.jsonl for content-type-aware mixing",
    )
    parser.add_argument(
        "--mix-config",
        default=None,
        help="Path to mix config JSON (enables domain-aware mixing)",
    )
    args = parser.parse_args()

    setup_logging("INFO")

    if args.enrichment or args.mix_config:
        path = build_mixed_splits_and_write(
            args.index,
            args.output_dir,
            enrichment_path=args.enrichment,
            mix_config_path=args.mix_config,
        )
    else:
        path = build_and_write_splits(args.index, args.output_dir, seed=args.seed)

    print(f"Splits written to: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

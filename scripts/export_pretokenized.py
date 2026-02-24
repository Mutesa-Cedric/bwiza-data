#!/usr/bin/env python3
"""Export pre-tokenized packed-sequence Parquet files for training.

Usage:
    python scripts/export_pretokenized.py \
        --splits-dir outputs/packaging/splits \
        --shard-dir outputs/shards \
        --output-dir outputs/packaging/parquet \
        --tokenizer Qwen/Qwen3-8B \
        --max-length 4096
"""

import argparse
import sys

from apps.common.logging import setup_logging
from apps.packaging.tokenize_export import export_all_splits


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export pre-tokenized packed Parquet for training"
    )
    parser.add_argument(
        "--splits-dir",
        required=True,
        help="Directory with train.txt, val.txt, test.txt",
    )
    parser.add_argument("--shard-dir", required=True, help="Local shard directory")
    parser.add_argument(
        "--output-dir",
        default="outputs/packaging/parquet",
        help="Output directory for Parquet files",
    )
    parser.add_argument(
        "--tokenizer",
        default="Qwen/Qwen3-8B",
        help="HuggingFace tokenizer name",
    )
    parser.add_argument(
        "--max-length",
        type=int,
        default=4096,
        help="Maximum sequence length (default 4096)",
    )
    args = parser.parse_args()

    setup_logging("INFO")

    results = export_all_splits(
        splits_dir=args.splits_dir,
        shard_dir=args.shard_dir,
        output_dir=args.output_dir,
        tokenizer_name=args.tokenizer,
        max_length=args.max_length,
    )

    total_seqs = sum(r.get("sequences", 0) for r in results.values())
    total_toks = sum(r.get("total_tokens", 0) for r in results.values())
    print(f"Exported {total_seqs} sequences ({total_toks:,} tokens) to {args.output_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Enrich documents with training metadata (token count, content type, etc.)."""

import argparse
import sys

from apps.common.logging import setup_logging
from apps.packaging.enrich import enrich_index


def main() -> int:
    parser = argparse.ArgumentParser(description="Enrich document metadata")
    parser.add_argument("--index", required=True, help="Path to dataset index JSONL")
    parser.add_argument("--shard-dir", required=True, help="Local shard directory")
    parser.add_argument(
        "--output",
        default="outputs/packaging/enrichment.jsonl",
        help="Output enrichment JSONL path",
    )
    parser.add_argument(
        "--tokenizer",
        default="Qwen/Qwen3-8B",
        help="HuggingFace tokenizer name",
    )
    args = parser.parse_args()

    setup_logging("INFO")

    path = enrich_index(
        index_path=args.index,
        shard_dir=args.shard_dir,
        output_path=args.output,
        tokenizer_name=args.tokenizer,
    )
    print(f"Enrichment written to {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

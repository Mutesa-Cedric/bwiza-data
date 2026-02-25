#!/usr/bin/env python3
"""Run books corpus ingestion pipeline (supports --resume)."""

import argparse
import sys

from apps.books_corpus.run import run_books_corpus
from apps.common.config import load_config
from apps.common.logging import setup_logging


def main() -> int:
    parser = argparse.ArgumentParser(description="Run books corpus pipeline")
    parser.add_argument(
        "--resume",
        default="",
        help="Resume a previous run by run_id",
    )
    args = parser.parse_args()

    cfg = load_config()
    setup_logging(cfg.logging.level)

    stats = run_books_corpus(cfg, resume_run_id=args.resume)

    d = stats.to_dict()
    print("\n--- Books Corpus Summary ---")
    for k, v in d.items():
        print(f"  {k}: {v}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

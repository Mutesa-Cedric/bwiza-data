#!/usr/bin/env python3
"""Run the parallel corpus builder (rw ↔ en)."""

import argparse
import sys

from apps.common.config import load_config
from apps.common.logging import setup_logging
from apps.parallel_corpus.run import run_parallel_corpus


def main() -> int:
    parser = argparse.ArgumentParser(description="Parallel corpus builder")
    parser.add_argument("--resume", default="", help="Resume a previous run by run_id")
    args = parser.parse_args()

    cfg = load_config()
    setup_logging(cfg.logging.level)

    stats = run_parallel_corpus(cfg, resume_run_id=args.resume)

    d = stats.to_dict()
    print("\n--- Parallel Corpus Summary ---")
    for k, v in d.items():
        print(f"  {k}: {v}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

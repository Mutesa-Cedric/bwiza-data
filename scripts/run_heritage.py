#!/usr/bin/env python3
"""Run Rwanda Heritage standalone miner (supports --resume, --dry-run)."""

import argparse
import sys

from apps.common.config import load_config
from apps.common.logging import setup_logging
from apps.heritage.run import run_heritage


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Rwanda Heritage miner")
    parser.add_argument(
        "--resume",
        default="",
        help="Resume a previous run by run_id",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run discovery only, skip harvest",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=0,
        help="Override max_listing_pages for discovery",
    )
    parser.add_argument(
        "--max-items",
        type=int,
        default=0,
        help="Override max_items for harvest",
    )
    args = parser.parse_args()

    cfg = load_config()
    setup_logging(cfg.logging.level)

    stats = run_heritage(
        cfg,
        resume_run_id=args.resume,
        dry_run=args.dry_run,
        max_pages_override=args.max_pages,
        max_items_override=args.max_items,
    )

    d = stats.to_dict()
    print("\n--- Heritage Miner Summary ---")
    for k, v in d.items():
        print(f"  {k}: {v}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

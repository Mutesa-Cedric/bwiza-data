#!/usr/bin/env python3
"""Run Wayback Machine mining (supports --resume and domain/year overrides)."""

import argparse
import sys

from apps.common.config import load_config
from apps.common.logging import setup_logging
from apps.wayback.run import run_wayback_miner


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Wayback Machine miner")
    parser.add_argument(
        "--resume",
        default="",
        help="Resume a previous run by run_id",
    )
    parser.add_argument(
        "--domains",
        nargs="+",
        help="Override wayback.domains (space-separated)",
    )
    parser.add_argument(
        "--from-year",
        type=int,
        help="Override wayback.from_year",
    )
    parser.add_argument(
        "--to-year",
        type=int,
        help="Override wayback.to_year",
    )
    args = parser.parse_args()

    cfg = load_config()
    setup_logging(cfg.logging.level)

    if args.domains:
        cfg.wayback.domains = args.domains
    if args.from_year is not None:
        cfg.wayback.from_year = args.from_year
    if args.to_year is not None:
        cfg.wayback.to_year = args.to_year

    stats = run_wayback_miner(cfg, resume_run_id=args.resume)

    d = stats.to_dict()
    print("\n--- Wayback Mining Summary ---")
    for k, v in d.items():
        print(f"  {k}: {v}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Run CC index-assisted mining (supports --resume)."""

import argparse
import sys

from apps.cc_index.run import run_cc_index
from apps.common.config import load_config
from apps.common.logging import setup_logging


def main() -> int:
    parser = argparse.ArgumentParser(description="Run CC index miner")
    parser.add_argument(
        "--resume",
        default="",
        help="Resume a previous run by run_id",
    )
    args = parser.parse_args()

    cfg = load_config()
    setup_logging(cfg.logging.level)

    stats = run_cc_index(cfg, resume_run_id=args.resume)

    d = stats.to_dict()
    print("\n--- CC Index Mining Summary ---")
    for k, v in d.items():
        print(f"  {k}: {v}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

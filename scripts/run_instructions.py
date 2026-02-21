#!/usr/bin/env python3
"""Run the instruction dataset builder."""

import argparse
import sys

from apps.common.config import load_config
from apps.common.logging import setup_logging
from apps.instructions.run import run_instructions


def main() -> int:
    parser = argparse.ArgumentParser(description="Instruction dataset builder")
    parser.add_argument("--resume", default="", help="Resume a previous run by run_id")
    args = parser.parse_args()

    cfg = load_config()
    setup_logging(cfg.logging.level)

    stats = run_instructions(cfg, resume_run_id=args.resume)

    d = stats.to_dict()
    print("\n--- Instructions Summary ---")
    for k, v in d.items():
        print(f"  {k}: {v}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

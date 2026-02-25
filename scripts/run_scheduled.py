#!/usr/bin/env python3
"""Cron-friendly scheduled runner for bwiza-data pipelines.

Usage:
    python scripts/run_scheduled.py --pipeline cc_miner
    python scripts/run_scheduled.py --pipeline targeted_crawler --resume <run_id>
    python scripts/run_scheduled.py --pipeline books_corpus --resume <run_id>
    python scripts/run_scheduled.py --pipeline parallel --resume <run_id>
    python scripts/run_scheduled.py --pipeline instructions --resume <run_id>

Exits 0 on success, 1 on failure. Safe for cron/GitHub Actions.
"""

import argparse
import sys
import traceback

from apps.common.config import load_config
from apps.common.logging import get_logger, setup_logging
from apps.common.run_lock import RunLockError, acquire_lock, release_lock

log = get_logger(__name__)

PIPELINES = {"cc_miner", "targeted_crawler", "books_corpus", "parallel", "instructions"}


def _run_pipeline(pipeline: str, cfg, resume_run_id: str = "") -> int:
    """Dispatch to the appropriate pipeline runner. Returns exit code."""
    if pipeline == "cc_miner":
        from apps.cc_miner.run_many import run_cc_miner

        stats = run_cc_miner(cfg, resume_run_id=resume_run_id)
    elif pipeline == "targeted_crawler":
        from apps.targeted_crawler.run import run_targeted_crawler

        stats = run_targeted_crawler(cfg, resume_run_id=resume_run_id)
    elif pipeline == "books_corpus":
        from apps.books_corpus.run import run_books_corpus

        stats = run_books_corpus(cfg, resume_run_id=resume_run_id)
    elif pipeline == "parallel":
        from apps.parallel_corpus.run import run_parallel_corpus

        stats = run_parallel_corpus(cfg, resume_run_id=resume_run_id)
    elif pipeline == "instructions":
        from apps.instructions.run import run_instructions

        stats = run_instructions(cfg, resume_run_id=resume_run_id)
    else:
        log.error("Unknown pipeline: %s", pipeline)
        return 1

    d = stats.to_dict()
    print(f"\n--- {pipeline} Summary ---")
    for k, v in d.items():
        print(f"  {k}: {v}")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Scheduled runner for bwiza-data pipelines")
    parser.add_argument(
        "--pipeline",
        required=True,
        choices=sorted(PIPELINES),
        help="Pipeline to run",
    )
    parser.add_argument(
        "--resume",
        default="",
        help="Resume a previous run by run_id",
    )
    parser.add_argument(
        "--lock-id",
        default="",
        help="Lock ID (defaults to pipeline name)",
    )
    args = parser.parse_args()

    cfg = load_config()
    setup_logging(cfg.logging.level)

    lock_id = args.lock_id or args.pipeline

    try:
        acquire_lock(lock_id)
    except RunLockError as exc:
        log.error("Cannot start: %s", exc)
        return 1

    try:
        return _run_pipeline(args.pipeline, cfg, resume_run_id=args.resume)
    except Exception:
        log.error("Pipeline %s failed:\n%s", args.pipeline, traceback.format_exc())
        return 1
    finally:
        release_lock(lock_id)


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Run CC miner on a single WET URL (for fast iteration)."""

import sys

from apps.common.config import load_config
from apps.common.dedup_exact import ExactDedupStore
from apps.common.filters.base import clear_registry
from apps.common.filters.quality import register_quality_filters
from apps.common.logging import setup_logging
from apps.cc_miner.run_one import run_one_wet
from apps.cc_miner.stats import RunStats
from apps.cc_miner.writer import LocalWriter


def main() -> int:
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <WET_URL>", file=sys.stderr)
        return 1

    wet_url = sys.argv[1]
    cfg = load_config()
    setup_logging(cfg.logging.level)

    clear_registry()
    register_quality_filters()

    run_id = "single_wet"
    writer = LocalWriter(cfg, run_id)
    dedup = ExactDedupStore()
    stats = RunStats()

    try:
        run_one_wet(wet_url, cfg, writer, dedup, stats)
    finally:
        writer.close()
        stats.write_json(cfg.output.local_dir, run_id)

    d = stats.to_dict()
    print(f"\n--- Stats ---")
    for k, v in d.items():
        print(f"  {k}: {v}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

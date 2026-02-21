#!/usr/bin/env python3
"""Run the targeted Rwanda domain crawler."""

import sys

from apps.common.config import load_config
from apps.common.logging import setup_logging
from apps.targeted_crawler.run import run_targeted_crawler


def main() -> int:
    cfg = load_config()
    setup_logging(cfg.logging.level)

    stats = run_targeted_crawler(cfg)

    d = stats.to_dict()
    print("\n--- Targeted Crawl Summary ---")
    for k, v in d.items():
        print(f"  {k}: {v}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

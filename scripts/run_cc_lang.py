#!/usr/bin/env python3
"""Run CC language-index mining for Kinyarwanda (or any target language).

Scans Common Crawl's columnar Parquet index for pages classified as the
target language, then fetches WARC records and runs quality pipeline.

Usage:
    python scripts/run_cc_lang.py --lang kin --max-crawls 10
    python scripts/run_cc_lang.py --resume <run_id>
"""

import argparse
import sys

from apps.cc_lang.run import run_cc_lang_miner
from apps.common.config import load_config
from apps.common.logging import setup_logging


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Mine Common Crawl for pages in a target language"
    )
    parser.add_argument(
        "--lang",
        default="kin",
        help="ISO 639-3 language code (default: kin for Kinyarwanda)",
    )
    parser.add_argument(
        "--max-crawls",
        type=int,
        default=10,
        help="Maximum number of CC crawls to scan (default: 10)",
    )
    parser.add_argument(
        "--resume",
        default="",
        help="Resume a previous run by run_id",
    )
    args = parser.parse_args()

    cfg = load_config()
    setup_logging(cfg.logging.level)

    stats = run_cc_lang_miner(
        cfg,
        lang_code=args.lang,
        max_crawls=args.max_crawls,
        resume_run_id=args.resume,
    )

    d = stats.to_dict()
    print("\n--- CC Language Mining Summary ---")
    for k, v in d.items():
        print(f"  {k}: {v}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

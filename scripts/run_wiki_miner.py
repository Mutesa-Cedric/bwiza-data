#!/usr/bin/env python3
"""Run Wikipedia miner: download rw dump → extract → quality pipeline → shards."""

import argparse

from apps.common.config import load_config
from apps.common.logging import get_logger
from apps.wiki_miner.run import run_wiki_miner

log = get_logger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Mine Kinyarwanda Wikipedia dump")
    parser.add_argument(
        "--config",
        default="configs/default.yaml",
        help="Config file path",
    )
    args = parser.parse_args()

    cfg = load_config(args.config)
    report = run_wiki_miner(cfg)
    log.info("Final report: %s", report.to_dict())


if __name__ == "__main__":
    main()

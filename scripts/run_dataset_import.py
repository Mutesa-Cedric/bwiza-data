#!/usr/bin/env python3
"""Run external dataset import: download from HuggingFace → quality pipeline → shards."""

import argparse

from apps.common.config import load_config
from apps.common.logging import get_logger
from apps.dataset_import.run import IMPORTERS, run_dataset_import

log = get_logger(__name__)


def main() -> None:
    choices = sorted(IMPORTERS) + ["all"]
    parser = argparse.ArgumentParser(description="Import external datasets")
    parser.add_argument(
        "--dataset",
        required=True,
        choices=choices,
        help="Dataset to import (or 'all' for all datasets)",
    )
    parser.add_argument(
        "--config",
        default="configs/default.yaml",
        help="Config file path",
    )
    args = parser.parse_args()

    cfg = load_config(args.config)

    if args.dataset == "all":
        datasets = sorted(IMPORTERS)
    else:
        datasets = [args.dataset]

    for ds_name in datasets:
        log.info("Starting import: %s", ds_name)
        report = run_dataset_import(cfg, ds_name)
        log.info("Report for %s: %s", ds_name, report.to_dict())


if __name__ == "__main__":
    main()

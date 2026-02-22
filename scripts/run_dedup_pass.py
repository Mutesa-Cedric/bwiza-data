#!/usr/bin/env python3
"""Run global dedup pass across all indexed shards."""

import argparse

from apps.common.config import load_config
from apps.common.dedup_store import DedupStore
from apps.common.logging import get_logger
from apps.packaging.dedup_pass import run_dedup_pass

log = get_logger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Global dedup pass at packaging time")
    parser.add_argument(
        "--index",
        default="outputs/datasets/pretrain/v1/index.jsonl",
        help="Path to dataset index file",
    )
    parser.add_argument(
        "--shard-dir",
        default="outputs/shards",
        help="Directory containing local shard files",
    )
    parser.add_argument(
        "--config",
        default="configs/default.yaml",
        help="Config file path",
    )
    parser.add_argument(
        "--output-dir",
        default="outputs/packaging",
        help="Output directory for dedup report",
    )
    args = parser.parse_args()

    cfg = load_config(args.config)
    store_path = cfg.dedup.store_path or "outputs/dedup_store.db"

    with DedupStore(
        db_path=store_path,
        fuzzy_threshold=cfg.dedup.fuzzy_threshold,
        fuzzy_num_perm=cfg.dedup.fuzzy_num_perm,
        enable_fuzzy=cfg.dedup.enable_fuzzy,
    ) as store:
        report = run_dedup_pass(
            index_path=args.index,
            shard_dir=args.shard_dir,
            store=store,
            output_dir=args.output_dir,
        )

    log.info("Final report: %s", report.to_dict())


if __name__ == "__main__":
    main()

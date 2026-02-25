#!/usr/bin/env python3
"""Full data pipeline: crawl → index → dedup → enrich → split → export.

Designed for long-running VPS execution. Run with:
    nohup python scripts/run_all.py > logs/run_all.log 2>&1 &

Strategy (ordered by expected yield):
  Tier 1: CC Language Index — scans CC Parquet index for content_languages='kin'
           Catches Kinyarwanda on ANY domain worldwide (jw.org, bible.com, etc.)
           WARC byte-range fetch from S3/HTTPS — no rate limiting.

  Tier 2: CC CDX Index — queries CC CDX for .rw domains + known news sites.
           Catches .rw pages that CLD2 may have misclassified.
           WARC byte-range fetch — no rate limiting.

  Tier 3: Targeted Crawler — live web crawl of 105 .rw domains.

  Tier 4: Wayback Machine — capped supplement (5K records max).
           Rate-limited by archive.org, so only for gap-filling.

After crawling, runs: index → dedup → enrich → split → export.
"""

import argparse
import logging
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

LOG_FMT = "[%(asctime)s] %(levelname)s %(message)s"


def _setup_logging(log_dir: Path) -> logging.Logger:
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("run_all")
    logger.setLevel(logging.INFO)
    # Console
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter(LOG_FMT, datefmt="%Y-%m-%d %H:%M:%S"))
    logger.addHandler(ch)
    # File
    fh = logging.FileHandler(log_dir / "pipeline.log")
    fh.setFormatter(logging.Formatter(LOG_FMT, datefmt="%Y-%m-%d %H:%M:%S"))
    logger.addHandler(fh)
    return logger


def _run(
    cmd: list[str],
    log_path: Path,
    logger: logging.Logger,
    label: str,
    timeout_hours: float = 0,
) -> bool:
    """Run a command, logging output to file. Returns True on success."""
    logger.info("Starting: %s", label)
    logger.info("  Command: %s", " ".join(cmd))
    logger.info("  Log: %s", log_path)

    timeout_s = int(timeout_hours * 3600) if timeout_hours else None
    try:
        with open(log_path, "w") as f:
            result = subprocess.run(
                cmd,
                stdout=f,
                stderr=subprocess.STDOUT,
                timeout=timeout_s,
            )
        if result.returncode == 0:
            logger.info("  ✓ %s completed successfully", label)
            return True
        else:
            logger.warning("  ✗ %s failed (exit %d)", label, result.returncode)
            return False
    except subprocess.TimeoutExpired:
        logger.warning("  ✗ %s timed out after %.1fh", label, timeout_hours)
        return False
    except Exception as exc:
        logger.error("  ✗ %s error: %s", label, exc)
        return False


def _run_parallel(
    tasks: list[tuple[list[str], Path, str, float]],
    logger: logging.Logger,
) -> dict[str, bool]:
    """Run multiple commands in parallel. Returns {label: success}."""
    import concurrent.futures

    results = {}

    def _task(cmd, log_path, label, timeout_hours):
        return label, _run(cmd, log_path, logger, label, timeout_hours)

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(tasks)) as pool:
        futures = []
        for cmd, log_path, label, timeout_h in tasks:
            futures.append(pool.submit(_task, cmd, log_path, label, timeout_h))

        for future in concurrent.futures.as_completed(futures):
            label, success = future.result()
            results[label] = success

    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Full bwiza-data pipeline")
    parser.add_argument(
        "--skip-crawl",
        action="store_true",
        help="Skip crawling stage (use existing shards)",
    )
    parser.add_argument(
        "--skip-packaging",
        action="store_true",
        help="Skip packaging stages (index → export)",
    )
    parser.add_argument(
        "--cc-lang-crawls",
        type=int,
        default=10,
        help="Number of CC crawls to scan for language index (default: 10)",
    )
    parser.add_argument(
        "--crawl-timeout",
        type=float,
        default=12.0,
        help="Max hours per crawler (default: 12)",
    )
    args = parser.parse_args()

    py = sys.executable
    ts = datetime.now().strftime("%Y%m%dT%H%M%S")
    log_dir = Path(f"logs/run_all_{ts}")
    logger = _setup_logging(log_dir)

    logger.info("=" * 60)
    logger.info("BWIZA-DATA FULL PIPELINE")
    logger.info("=" * 60)
    start = time.time()

    # ── STAGE 1: CRAWL ──────────────────────────────────────
    if not args.skip_crawl:
        logger.info("")
        logger.info("STAGE 1: DATA COLLECTION")
        logger.info("-" * 40)

        crawl_tasks = [
            # Tier 1: CC Language Index (highest yield — global Kinyarwanda)
            (
                [
                    py,
                    "scripts/run_cc_lang.py",
                    "--lang",
                    "kin",
                    "--max-crawls",
                    str(args.cc_lang_crawls),
                ],
                log_dir / "cc_lang.log",
                "CC Language Index (Tier 1)",
                args.crawl_timeout,
            ),
            # Tier 2: CC CDX Index (.rw domains + news sites)
            (
                [py, "scripts/run_cc_index.py"],
                log_dir / "cc_index.log",
                "CC CDX Index (Tier 2)",
                args.crawl_timeout,
            ),
            # Tier 3: Targeted Crawler (live .rw web)
            (
                [py, "scripts/run_targeted_crawler.py"],
                log_dir / "targeted.log",
                "Targeted Crawler (Tier 3)",
                args.crawl_timeout,
            ),
            # Tier 4: Wayback (supplement, capped)
            (
                [py, "scripts/run_wayback_miner.py"],
                log_dir / "wayback.log",
                "Wayback (Tier 4, capped)",
                args.crawl_timeout,
            ),
        ]

        results = _run_parallel(crawl_tasks, logger)
        failed = [k for k, v in results.items() if not v]
        if failed:
            logger.warning("Failed crawlers: %s — continuing with available data", failed)

    # ── STAGE 2: PACKAGING ───────────────────────────────────
    if not args.skip_packaging:
        logger.info("")
        logger.info("STAGE 2: PACKAGING PIPELINE")
        logger.info("-" * 40)

        # 2a. Build index
        _run(
            [
                py,
                "scripts/build_index.py",
                "--dataset",
                "pretrain",
                "--bucket",
                "bwiza-test-bucket",
                "--version",
                "v1",
                "--manifest-dir",
                "manifests/shards",
                "--output-dir",
                "outputs/datasets",
            ],
            log_dir / "build_index.log",
            logger,
            "Build index",
        )

        index_path = "outputs/datasets/pretrain/v1/index.jsonl"
        if Path(index_path).exists():
            n = sum(1 for _ in open(index_path))
            logger.info("  Index: %d entries", n)

        # 2b. Global dedup
        _run(
            [
                py,
                "scripts/run_dedup_pass.py",
                "--index",
                index_path,
                "--shard-dir",
                "outputs/shards",
                "--output-dir",
                "outputs/packaging",
            ],
            log_dir / "dedup.log",
            logger,
            "Global dedup",
        )

        # 2c. Enrich metadata
        _run(
            [
                py,
                "scripts/enrich_metadata.py",
                "--index",
                index_path,
                "--shard-dir",
                "outputs/shards",
                "--output",
                "outputs/packaging/enrichment.jsonl",
                "--tokenizer",
                "Qwen/Qwen3-8B",
            ],
            log_dir / "enrich.log",
            logger,
            "Enrich metadata",
        )

        # 2d. Build splits
        _run(
            [
                py,
                "scripts/build_splits.py",
                "--index",
                index_path,
                "--output-dir",
                "outputs/packaging/splits",
                "--enrichment",
                "outputs/packaging/enrichment.jsonl",
            ],
            log_dir / "splits.log",
            logger,
            "Build splits",
        )

        # 2e. Export Parquet
        _run(
            [
                py,
                "scripts/export_pretokenized.py",
                "--splits-dir",
                "outputs/packaging/splits",
                "--shard-dir",
                "outputs/shards",
                "--output-dir",
                "outputs/packaging/parquet",
                "--tokenizer",
                "Qwen/Qwen3-8B",
                "--max-length",
                "4096",
            ],
            log_dir / "export.log",
            logger,
            "Export Parquet",
        )

        # 2f. Validation
        _run(
            [
                py,
                "scripts/tokenizer_validation.py",
                "--shard-dir",
                "outputs/shards",
                "--tokenizer",
                "Qwen/Qwen3-8B",
                "--max-docs-per-source",
                "500",
            ],
            log_dir / "validation.log",
            logger,
            "Tokenizer validation",
        )

    # ── SUMMARY ──────────────────────────────────────────────
    elapsed = time.time() - start
    logger.info("")
    logger.info("=" * 60)
    logger.info("PIPELINE COMPLETE (%.1f hours)", elapsed / 3600)
    logger.info("=" * 60)

    shard_count = len(list(Path("outputs/shards").rglob("*.jsonl.zst")))
    logger.info("  Shards: %d files", shard_count)

    index_path = Path("outputs/datasets/pretrain/v1/index.jsonl")
    if index_path.exists():
        logger.info("  Index: %d entries", sum(1 for _ in open(index_path)))

    enrichment = Path("outputs/packaging/enrichment.jsonl")
    if enrichment.exists():
        logger.info("  Enrichment: %d docs", sum(1 for _ in open(enrichment)))

    parquet_dir = Path("outputs/packaging/parquet")
    if parquet_dir.exists():
        total = sum(f.stat().st_size for f in parquet_dir.glob("*.parquet"))
        logger.info("  Parquet: %.1f MB", total / 1024 / 1024)

    logger.info("  Logs: %s", log_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())

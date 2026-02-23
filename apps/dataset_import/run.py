"""End-to-end dataset import runner: load → quality pipeline → dedup → shard → report."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from apps.common.config_types import AppConfig
from apps.common.dedup_factory import create_dedup
from apps.common.filters.base import clear_registry
from apps.common.filters.quality import register_quality_filters
from apps.common.logging import get_logger
from apps.common.manifest import append_manifest_entry
from apps.common.shard_writer import ShardWriter
from apps.dataset_import.base import DatasetImporter, ImportRunReport, import_and_process
from apps.dataset_import.kinnews import KinNewsImporter
from apps.dataset_import.mbazanlp import MbazaNLPImporter

log = get_logger(__name__)

IMPORTERS: dict[str, type[DatasetImporter]] = {
    "mbazanlp": MbazaNLPImporter,
    "kinnews": KinNewsImporter,
}


def get_importer(name: str) -> DatasetImporter:
    """Instantiate an importer by short name."""
    cls = IMPORTERS.get(name)
    if cls is None:
        raise ValueError(f"Unknown dataset: {name!r}. Available: {sorted(IMPORTERS)}")
    return cls()


def run_dataset_import(cfg: AppConfig, dataset_name: str) -> ImportRunReport:
    """Run a single dataset import through the full pipeline."""
    clear_registry()
    register_quality_filters()

    importer = get_importer(dataset_name)
    source = importer.name
    run_id = f"{source}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"

    log.info("Dataset import run=%s source=%s", run_id, source)

    dedup = create_dedup(cfg.dedup)
    writer = ShardWriter(cfg.sharding, source=source, run_id=run_id)

    def on_shard_closed(meta):
        append_manifest_entry(run_id, meta, source=source)

    try:
        report = import_and_process(importer, cfg, dedup, writer, on_shard_closed, run_id=run_id)
    except KeyboardInterrupt:
        log.warning("Interrupted. Flushing output.")
        report = ImportRunReport()
    finally:
        final_meta = writer.close()
        if final_meta is not None:
            on_shard_closed(final_meta)
        dedup.close()

    # Write report
    report_dir = Path(cfg.dataset_import.output_dir) / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"{run_id}.json"
    with open(report_path, "w") as f:
        json.dump(report.to_dict(), f, indent=2)

    log.info(
        "Dataset import done: seen=%d kept=%d chars=%d keep_rate=%.2f%%",
        report.docs_seen,
        report.docs_kept,
        report.total_kept_chars,
        (report.to_dict()["keep_rate"] * 100),
    )
    log.info("Report: %s", report_path)

    return report

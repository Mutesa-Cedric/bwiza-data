"""Build dataset index from run manifests."""

import json
from pathlib import Path

from apps.common.dataset_index import (
    DatasetIndexEntry,
    dataset_for_source,
    write_index,
)
from apps.common.logging import get_logger
from apps.common.s3_paths import shard_key

log = get_logger(__name__)

# S3 prefix per source (must match what pipelines use during upload)
SOURCE_S3_PREFIX: dict[str, str] = {
    "commoncrawl": "bwiza/cc/v1/",
    "targeted_web": "bwiza/curated/v1/targeted_web/",
    "wayback": "bwiza/curated/v1/wayback/",
    "cc_index": "bwiza/curated/v1/cc_index/",
    "books_corpus": "bwiza/curated/v1/books/",
    "parallel_web": "bwiza/supervision/v1/parallel/",
    "instructions_rw": "bwiza/supervision/v1/instructions/",
    "wikipedia": "bwiza/wiki/v1/",
    "mbazanlp_v01.1": "bwiza/external/v1/mbazanlp/",
    "kinnews": "bwiza/external/v1/kinnews/",
}


def build_index(
    dataset: str,
    s3_bucket: str,
    version: str = "v1",
    manifest_dir: str = "manifests/shards",
) -> list[DatasetIndexEntry]:
    """Build a dataset index by scanning all manifest files.

    Filters to entries matching the given dataset type, skips entries
    with empty checksums, and returns sorted entries.
    """
    manifest_path = Path(manifest_dir)
    if not manifest_path.exists():
        log.warning("Manifest directory not found: %s", manifest_dir)
        return []

    entries: list[DatasetIndexEntry] = []

    for mf in sorted(manifest_path.glob("*.jsonl")):
        with open(mf, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)

                source = record.get("source", "")
                try:
                    ds = dataset_for_source(source)
                except ValueError:
                    log.warning("Unknown source %r in %s, skipping", source, mf.name)
                    continue

                if ds != dataset:
                    continue

                checksum = record.get("checksum", "")
                if not checksum:
                    log.warning(
                        "Skipping entry without checksum: %s in %s",
                        record.get("filename", "?"),
                        mf.name,
                    )
                    continue

                run_id = record.get("run_id", "")
                filename = record.get("filename", "")
                prefix = SOURCE_S3_PREFIX.get(source, "bwiza/unknown/")
                s3_key_val = shard_key(prefix, run_id, filename)

                entry = DatasetIndexEntry(
                    dataset=dataset,
                    version=version,
                    run_id=run_id,
                    source=source,
                    shard_name=filename,
                    s3_bucket=s3_bucket,
                    s3_key=s3_key_val,
                    bytes=record.get("bytes", 0),
                    records=record.get("records_count", 0),
                    token_estimate=record.get("token_estimate", 0),
                    checksum_sha256=checksum,
                    created_at=record.get("created_at", ""),
                )
                entries.append(entry)

    # Deterministic sort
    entries.sort(key=lambda e: (e.run_id, e.shard_name))

    log.info("Built index for %s: %d entries from %s", dataset, len(entries), manifest_dir)
    return entries


def build_and_write_index(
    dataset: str,
    s3_bucket: str,
    version: str = "v1",
    manifest_dir: str = "manifests/shards",
    output_dir: str = "outputs/datasets",
) -> Path:
    """Build index and write to outputs/datasets/{dataset}/{version}/index.jsonl."""
    entries = build_index(dataset, s3_bucket, version, manifest_dir)
    out_path = Path(output_dir) / dataset / version / "index.jsonl"
    write_index(entries, out_path)
    return out_path

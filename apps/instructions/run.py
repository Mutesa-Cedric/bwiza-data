"""End-to-end instruction dataset builder."""

import hashlib
from collections import Counter
from datetime import datetime, timezone

from apps.cc_miner.stats import RunStats
from apps.common.config_types import AppConfig
from apps.common.logging import get_logger
from apps.common.manifest import append_manifest_entry
from apps.common.s3_paths import shard_key
from apps.common.s3_upload import upload_file, verify_upload
from apps.common.shard_writer import ShardWriter
from apps.instructions.generate import generate_synthetic, load_gold_seeds
from apps.instructions.validate import validate_instruction

log = get_logger(__name__)

S3_PREFIX_INSTRUCTIONS = "bwiza/supervision/v1/instructions/"


def _dedup_hash(prompt: str, response: str) -> str:
    content = f"{prompt}||{response}"
    return hashlib.sha256(content.encode()).hexdigest()


def run_instructions(cfg: AppConfig) -> RunStats:
    """Run the instruction dataset builder end-to-end."""
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    icfg = cfg.instructions
    stats = RunStats()
    task_type_counts: Counter = Counter()

    # Collect all candidate examples
    examples = []
    examples.extend(load_gold_seeds(icfg.seed_file))
    examples.extend(generate_synthetic())

    log.info(
        "Instruction candidates: %d total (%d gold + synthetic)",
        len(examples),
        len(examples),
    )

    writer = ShardWriter(cfg.sharding, source=icfg.output_source, run_id=run_id)

    # S3 setup
    s3_client = None
    if cfg.s3.enabled:
        from apps.common.s3_client import get_s3_client

        s3_client = get_s3_client(cfg.s3)

    def on_shard_closed(meta):
        append_manifest_entry(run_id, meta, source=icfg.output_source)
        if s3_client is not None:
            key = shard_key(S3_PREFIX_INSTRUCTIONS, run_id, meta.filename)
            try:
                result = upload_file(s3_client, meta.path, cfg.s3.bucket, key, cfg.s3)
                if not result.skipped and cfg.s3.verify_after_upload:
                    if not verify_upload(s3_client, meta.path, cfg.s3.bucket, key):
                        log.error("Verification failed for %s", key)
            except Exception:
                log.exception("S3 upload failed for %s", meta.filename)

    seen_hashes: set[str] = set()

    for ex in examples:
        stats.docs_seen += 1

        # Skip synthetic with empty responses (prompt-only scaffolding)
        if not ex.response:
            stats.reject_reasons["reject.empty_response"] += 1
            continue

        # Validate
        ok, reason = validate_instruction(ex, icfg)
        if not ok:
            stats.reject_reasons[reason] += 1
            continue

        # Dedup
        h = _dedup_hash(ex.prompt, ex.response)
        if h in seen_hashes:
            stats.duplicates += 1
            stats.reject_reasons["reject.duplicate"] += 1
            continue
        seen_hashes.add(h)

        # Write to shard
        shard_result = writer.write(ex.to_json())
        stats.docs_kept += 1
        stats.total_kept_chars += len(ex.prompt) + len(ex.response)
        task_type_counts[ex.task_type] += 1

        if shard_result is not None:
            on_shard_closed(shard_result)

        # Stop if we hit target count
        if icfg.target_count > 0 and stats.docs_kept >= icfg.target_count:
            log.info("Reached target count %d", icfg.target_count)
            break

    # Close final shard
    final_meta = writer.close()
    if final_meta is not None:
        on_shard_closed(final_meta)
    stats.write_json("outputs/instructions", run_id)

    log.info(
        "Instructions complete: kept=%d seen=%d dupes=%d task_types=%s",
        stats.docs_kept,
        stats.docs_seen,
        stats.duplicates,
        dict(task_type_counts.most_common()),
    )

    return stats

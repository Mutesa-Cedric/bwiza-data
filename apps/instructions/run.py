"""End-to-end instruction dataset builder (resumable)."""

import hashlib
from collections import Counter
from datetime import datetime, timezone

from apps.cc_miner.stats import RunStats
from apps.common.config_fingerprint import fingerprint_config
from apps.common.config_types import AppConfig
from apps.common.guardrails import GuardrailChecker
from apps.common.logging import get_logger
from apps.common.manifest import append_manifest_entry
from apps.common.run_state import RunState
from apps.common.run_state_store import load_done_set, load_state, mark_done, save_state
from apps.common.run_state_sync import upload_done_list, upload_state
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


def run_instructions(cfg: AppConfig, resume_run_id: str = "") -> RunStats:
    """Run the instruction dataset builder end-to-end.

    If resume_run_id is provided, resumes that run (skipping done examples).
    """
    icfg = cfg.instructions

    # Load or create RunState
    state = None
    if resume_run_id:
        state = load_state(resume_run_id)
        if state is None:
            log.warning("No state found for %s, starting fresh", resume_run_id)

    if state is not None:
        run_id = state.run_id
        done_set = load_done_set(run_id)
        log.info(
            "Resuming instructions run=%s, %d examples already done",
            run_id,
            len(done_set),
        )
    else:
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        done_set = set()
        state = RunState(
            run_id=run_id,
            pipeline="instructions",
            source="instructions_rw",
            config_fingerprint=fingerprint_config(cfg),
        )

    state.start()
    save_state(state)

    stats = RunStats()
    task_type_counts: Counter = Counter()
    guardrails = GuardrailChecker(cfg.guardrails)

    # Collect all candidate examples
    examples = []
    examples.extend(load_gold_seeds(icfg.seed_file))
    examples.extend(generate_synthetic())

    state.items_total = len(examples)
    save_state(state)

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

    def _sync_state_to_s3():
        if s3_client is not None:
            try:
                upload_state(s3_client, cfg.s3.bucket, state)
                done_file = f"manifests/state/{run_id}.done.txt"
                upload_done_list(s3_client, cfg.s3.bucket, run_id, done_file)
            except Exception:
                log.exception("S3 state sync failed")

    def on_shard_closed(meta):
        append_manifest_entry(run_id, meta, source=icfg.output_source)
        state.shards_closed += 1
        state.bytes_written += meta.bytes
        state.last_shard_name = meta.filename
        save_state(state)
        if s3_client is not None:
            key = shard_key(S3_PREFIX_INSTRUCTIONS, run_id, meta.filename)
            try:
                result = upload_file(s3_client, meta.path, cfg.s3.bucket, key, cfg.s3)
                if not result.skipped and cfg.s3.verify_after_upload:
                    if not verify_upload(s3_client, meta.path, cfg.s3.bucket, key):
                        log.error("Verification failed for %s", key)
            except Exception:
                log.exception("S3 upload failed for %s", meta.filename)
            state.uploaded_shards += 1
            _sync_state_to_s3()

    seen_hashes: set[str] = set()

    try:
        for ex in examples:
            stats.docs_seen += 1
            state.current_item = ex.id

            # Skip if already done (resume)
            if ex.id in done_set:
                state.items_skipped += 1
                continue

            # Skip synthetic with empty responses (prompt-only scaffolding)
            if not ex.response:
                stats.reject_reasons["reject.empty_response"] += 1
                continue

            # Validate
            ok, reason = validate_instruction(ex, icfg)
            if not ok:
                stats.reject_reasons[reason] += 1
                state.items_done += 1
                mark_done(run_id, ex.id)
                continue

            # Dedup
            h = _dedup_hash(ex.prompt, ex.response)
            if h in seen_hashes:
                stats.duplicates += 1
                stats.reject_reasons["reject.duplicate"] += 1
                state.items_done += 1
                mark_done(run_id, ex.id)
                continue
            seen_hashes.add(h)

            # Write to shard
            shard_result = writer.write(ex.to_json())
            stats.docs_kept += 1
            stats.total_kept_chars += len(ex.prompt) + len(ex.response)
            task_type_counts[ex.task_type] += 1
            state.items_done += 1
            mark_done(run_id, ex.id)

            if shard_result is not None:
                on_shard_closed(shard_result)

            # Check guardrails
            triggered, greason = guardrails.check(state)
            if triggered:
                log.info("Guardrail triggered: %s", greason)
                state.pause(greason)
                break

            # Stop if we hit target count
            if icfg.target_count > 0 and stats.docs_kept >= icfg.target_count:
                log.info("Reached target count %d", icfg.target_count)
                break

        if state.status == "running":
            state.complete()
    except KeyboardInterrupt:
        log.warning("Interrupted. Flushing output.")
        state.pause("interrupted")
    except Exception as exc:
        state.fail(str(exc))
        raise
    finally:
        final_meta = writer.close()
        if final_meta is not None:
            on_shard_closed(final_meta)
        state.current_item = ""
        save_state(state)
        _sync_state_to_s3()
        stats.write_json("outputs/instructions", run_id)

    log.info(
        "Instructions complete: kept=%d seen=%d dupes=%d task_types=%s",
        stats.docs_kept,
        stats.docs_seen,
        stats.duplicates,
        dict(task_type_counts.most_common()),
    )

    return stats

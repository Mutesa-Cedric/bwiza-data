"""End-to-end CC language-index mining runner.

Scans the Common Crawl columnar index for pages classified as the target
language (default: Kinyarwanda / 'kin'), then fetches WARC records and
runs them through the quality pipeline.
"""

from __future__ import annotations

import queue
import threading
from datetime import datetime, timezone

from apps.cc_index.pipeline import process_warc_html
from apps.cc_index.warc_fetch import WARCFetchResult, fetch_warc_record
from apps.cc_index.warc_parse import parse_warc_record
from apps.cc_lang.index_scan import (
    LangIndexRecord,
    discover_crawl_ids,
    scan_crawl_for_language,
)
from apps.cc_miner.stats import RunStats
from apps.common.concurrency import BoundedWorkerPool
from apps.common.config_fingerprint import fingerprint_config
from apps.common.config_types import AppConfig, CCIndexConfig
from apps.common.dedup_factory import create_dedup
from apps.common.filters.base import clear_registry
from apps.common.filters.quality import register_quality_filters
from apps.common.guardrails import GuardrailChecker
from apps.common.logging import get_logger
from apps.common.manifest import append_manifest_entry
from apps.common.run_state import RunState
from apps.common.run_state_store import load_done_set, load_state, mark_done, save_state
from apps.common.shard_writer import ShardWriter
from apps.common.url_utils import get_domain

log = get_logger(__name__)

OUTPUT_SOURCE = "cc_lang"


def _done_key(rec: LangIndexRecord) -> str:
    return f"{rec.warc_filename}:{rec.warc_record_offset}"


def _fetch_one(
    rec: LangIndexRecord, cfg: CCIndexConfig
) -> tuple[LangIndexRecord, WARCFetchResult]:
    result = fetch_warc_record(
        rec.warc_filename, rec.warc_record_offset, rec.warc_record_length, cfg
    )
    return rec, result


def run_cc_lang_miner(
    cfg: AppConfig,
    lang_code: str = "kin",
    max_crawls: int = 10,
    resume_run_id: str = "",
) -> RunStats:
    """Mine Common Crawl for pages in a specific language.

    1. Discover crawls with language annotations (2018-39+)
    2. Scan columnar index Parquet files for content_languages matching lang_code
    3. Fetch WARC records concurrently
    4. Extract -> LID -> quality -> dedup -> shard
    """
    clear_registry()
    register_quality_filters()

    icfg = cfg.cc_index  # reuse CC index config for WARC fetch settings

    # Load or create RunState
    state = None
    if resume_run_id:
        state = load_state(resume_run_id)
        if state is None:
            log.warning("No state found for %s, starting fresh", resume_run_id)

    if state is not None:
        run_id = state.run_id
        done_set = load_done_set(run_id)
        log.info("Resuming cc_lang run=%s, %d already done", run_id, len(done_set))
    else:
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        done_set: set[str] = set()
        state = RunState(
            run_id=run_id,
            pipeline="cc_lang",
            source=OUTPUT_SOURCE,
            config_fingerprint=fingerprint_config(cfg),
        )

    state.start()
    save_state(state)

    # Discover crawls
    crawl_ids = discover_crawl_ids(max_crawls=max_crawls)
    log.info("Scanning %d crawls for lang=%s", len(crawl_ids), lang_code)

    # Set up components
    guardrails = GuardrailChecker(cfg.guardrails)
    dedup = create_dedup(cfg.dedup)
    stats = RunStats()
    writer = ShardWriter(cfg.sharding, source=OUTPUT_SOURCE, run_id=run_id)
    pool = BoundedWorkerPool(max_workers=icfg.warc_concurrency, name="cc_lang")
    guardrail_hit = False

    def on_shard_closed(meta):
        append_manifest_entry(run_id, meta, source=OUTPUT_SOURCE)
        state.shards_closed += 1
        state.bytes_written += meta.bytes
        state.last_shard_name = meta.filename
        save_state(state)

    # Use a bounded queue so scanning runs concurrently with WARC fetching.
    # The scanner pushes records into the queue from a background thread;
    # the main thread reads them, batches, and processes.
    scan_q: queue.Queue[LangIndexRecord | None] = queue.Queue(
        maxsize=icfg.warc_concurrency * 4,
    )

    def _scan_thread() -> None:
        try:
            for crawl_id in crawl_ids:
                log.info("--- Scanning crawl %s ---", crawl_id)
                for rec in scan_crawl_for_language(crawl_id, lang_code):
                    if _done_key(rec) in done_set:
                        state.items_skipped += 1
                        continue
                    scan_q.put(rec)
        except Exception:
            log.exception("Scanner thread failed")
        finally:
            scan_q.put(None)  # sentinel

    scanner = threading.Thread(target=_scan_thread, daemon=True)

    try:
        scanner.start()
        batch: list[LangIndexRecord] = []

        while not guardrail_hit:
            try:
                rec = scan_q.get(timeout=120)
            except queue.Empty:
                if not scanner.is_alive():
                    break
                continue

            if rec is None:
                break

            batch.append(rec)

            if len(batch) >= icfg.warc_concurrency:
                guardrail_hit = _process_batch(
                    batch,
                    pool,
                    icfg,
                    cfg,
                    dedup,
                    guardrails,
                    writer,
                    stats,
                    state,
                    run_id,
                    on_shard_closed,
                )
                batch = []

        # Flush remaining batch
        if batch and not guardrail_hit:
            guardrail_hit = _process_batch(
                batch,
                pool,
                icfg,
                cfg,
                dedup,
                guardrails,
                writer,
                stats,
                state,
                run_id,
                on_shard_closed,
            )

        if state.status == "running":
            state.complete()
    except KeyboardInterrupt:
        log.warning("Interrupted. Flushing output.")
        state.pause("interrupted")
    except Exception as exc:
        state.fail(str(exc))
        raise
    finally:
        pool.shutdown(wait=True)
        final_meta = writer.close()
        if final_meta is not None:
            on_shard_closed(final_meta)
        dedup.close()
        state.current_item = ""
        save_state(state)
        stats.write_json("outputs/cc_lang", run_id)

    log.info(
        "CC lang mining complete: kept=%d seen=%d dupes=%d",
        stats.docs_kept,
        stats.docs_seen,
        stats.duplicates,
    )
    return stats


def _process_batch(
    batch: list[LangIndexRecord],
    pool: BoundedWorkerPool,
    icfg: CCIndexConfig,
    cfg: AppConfig,
    dedup,
    guardrails: GuardrailChecker,
    writer: ShardWriter,
    stats: RunStats,
    state: RunState,
    run_id: str,
    on_shard_closed,
) -> bool:
    """Fetch + process a batch of records. Returns True if guardrail hit."""
    for rec in batch:
        pool.submit(_fetch_one, rec, icfg)
    fetch_results = pool.drain()

    for rec, warc_result in fetch_results:
        stats.docs_seen += 1
        state.items_done += 1
        state.current_item = rec.url

        url_domain = get_domain(rec.url)
        if url_domain:
            stats.domain_seen[url_domain] += 1

        if not warc_result.ok:
            stats.reject_reasons[f"reject.warc_fetch.{warc_result.error}"] += 1
            mark_done(run_id, _done_key(rec))
            continue

        # Parse WARC record
        parsed = parse_warc_record(warc_result.raw_data)
        if not parsed.ok:
            stats.reject_reasons[f"reject.warc_parse.{parsed.error}"] += 1
            mark_done(run_id, _done_key(rec))
            continue

        # Process through quality pipeline
        doc, decision = process_warc_html(
            parsed.body,
            rec.url,
            "cc_lang",
            cfg,
            dedup,
        )

        if doc is None:
            stats.reject_reasons[decision.reason] += 1
            if "dedup" in decision.reason:
                stats.duplicates += 1
            mark_done(run_id, _done_key(rec))
            continue

        # Override source to cc_lang
        doc.source = OUTPUT_SOURCE
        shard_result = writer.write(doc.to_json())
        stats.docs_kept += 1
        stats.total_kept_chars += len(doc.text)
        if url_domain:
            stats.domain_kept[url_domain] += 1
        mark_done(run_id, _done_key(rec))

        if shard_result is not None:
            on_shard_closed(shard_result)

        # Check guardrails
        triggered, reason = guardrails.check(state)
        if triggered:
            log.info("Guardrail triggered: %s", reason)
            state.pause(reason)
            return True

    # Progress logging
    if state.items_done % 100 < len(batch):
        save_state(state)
        log.info(
            "Progress: processed=%d kept=%d",
            state.items_done,
            stats.docs_kept,
        )

    return False

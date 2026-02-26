"""End-to-end heritage miner runner (resumable, two-stage)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from apps.cc_miner.stats import RunStats
from apps.common.config_fingerprint import fingerprint_config
from apps.common.config_types import AppConfig
from apps.common.dedup_factory import create_dedup
from apps.common.filters.base import clear_registry
from apps.common.filters.quality import register_quality_filters
from apps.common.guardrails import GuardrailChecker
from apps.common.logging import get_logger
from apps.common.manifest import append_manifest_entry
from apps.common.run_state import RunState
from apps.common.run_state_store import load_done_set, load_state, mark_done, save_state
from apps.common.run_state_sync import upload_done_list, upload_state
from apps.common.s3_paths import shard_key
from apps.common.s3_upload import upload_file, verify_upload
from apps.common.shard_writer import ShardWriter
from apps.common.url_utils import get_domain
from apps.heritage.discovery import (
    load_discovery_index,
    run_discovery,
    save_discovery_index,
)
from apps.heritage.harvest import (
    DeadLetterEntry,
    harvest_url,
    save_dead_letter,
)
from apps.targeted_crawler.rate_limit import DomainRateLimiter

log = get_logger(__name__)


def _make_fetch_cfg(cfg: AppConfig):
    from apps.common.config_types import TargetedConfig

    hcfg = cfg.heritage
    return TargetedConfig(
        request_timeout_s=hcfg.request_timeout_s,
        max_retries=hcfg.max_retries,
        retry_backoff_s=hcfg.retry_backoff_s,
        max_response_bytes=hcfg.max_response_bytes,
        user_agent=hcfg.user_agent,
        allowed_content_types=hcfg.allowed_content_types,
    )


def run_heritage(
    cfg: AppConfig,
    resume_run_id: str = "",
    dry_run: bool = False,
    max_pages_override: int = 0,
    max_items_override: int = 0,
) -> RunStats:
    """Run the heritage miner pipeline end-to-end.

    Stage 1: Discovery — enumerate all URLs on rwandaheritage.gov.rw
    Stage 2: Harvest — fetch, extract, filter, and shard content
    """
    clear_registry()
    register_quality_filters()

    hcfg = cfg.heritage

    # Apply heritage-specific overrides to shared config
    cfg.lid.min_confidence = hcfg.min_lid_confidence
    if hcfg.max_chars:
        cfg.filters.max_chars = hcfg.max_chars
    if hcfg.max_word_ngram_rep_2:
        cfg.filters.max_word_ngram_rep_2 = hcfg.max_word_ngram_rep_2
    if hcfg.max_word_ngram_rep_3:
        cfg.filters.max_word_ngram_rep_3 = hcfg.max_word_ngram_rep_3
    if hcfg.max_word_ngram_rep_4:
        cfg.filters.max_word_ngram_rep_4 = hcfg.max_word_ngram_rep_4

    # Apply CLI overrides
    if max_pages_override > 0:
        hcfg.max_listing_pages = max_pages_override
    if max_items_override > 0:
        hcfg.max_items = max_items_override

    # State management
    state = None
    if resume_run_id:
        state = load_state(resume_run_id)
        if state is None:
            log.warning("No state found for %s, starting fresh", resume_run_id)

    if state is not None:
        run_id = state.run_id
        done_set = load_done_set(run_id)
        log.info("Resuming heritage run=%s, %d URLs already done", run_id, len(done_set))
    else:
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        done_set = set()
        state = RunState(
            run_id=run_id,
            pipeline="heritage",
            source=hcfg.output_source,
            config_fingerprint=fingerprint_config(cfg),
        )

    state.start()
    save_state(state)

    output_dir = Path(f"outputs/heritage/{run_id}")
    output_dir.mkdir(parents=True, exist_ok=True)

    stats = RunStats()
    discovery_meta: dict = {}

    # ── STAGE 1: DISCOVERY ─────────────────────────────────
    log.info("=== STAGE 1: DISCOVERY ===")

    # Check if we have a saved discovery index from a previous run
    discovery_index_path = output_dir / f"{run_id}_discovery_index.jsonl"
    if discovery_index_path.exists() and resume_run_id:
        log.info("Loading saved discovery index: %s", discovery_index_path)
        discovered_urls = load_discovery_index(discovery_index_path)
        log.info("Loaded %d previously discovered URLs", len(discovered_urls))
        discovery_meta = {"loaded_from_cache": True, "total_urls": len(discovered_urls)}
    else:
        discovery_result = run_discovery(cfg, discovery_done=done_set)
        discovered_urls = discovery_result.discovered
        save_discovery_index(discovery_result, output_dir, run_id)

        discovery_meta = {
            "pages_crawled": discovery_result.pages_crawled,
            "news": discovery_result.news_count,
            "pdf": discovery_result.pdf_count,
            "listing": discovery_result.listing_count,
            "static": discovery_result.static_count,
            "total_urls": len(discovered_urls),
        }

        state.meta["discovery_pages_crawled"] = discovery_result.pages_crawled
        state.meta["discovery_news"] = discovery_result.news_count
        state.meta["discovery_pdf"] = discovery_result.pdf_count
        state.meta["discovery_listing"] = discovery_result.listing_count
        state.meta["discovery_static"] = discovery_result.static_count
        save_state(state)

    if dry_run:
        log.info("DRY RUN — skipping harvest stage")
        state.complete()
        save_state(state)
        _write_heritage_stats(stats, discovery_meta, [], False, output_dir, run_id)
        return stats

    # ── STAGE 2: HARVEST ───────────────────────────────────
    log.info("=== STAGE 2: HARVEST ===")

    # Filter to harvestable content (news + pdf + static pages)
    harvestable = [
        item for item in discovered_urls if item.url_class in ("news", "pdf", "document", "static")
    ]
    pending = [item for item in harvestable if item.url not in done_set]

    state.items_total = len(harvestable)
    if len(pending) < len(harvestable):
        skipped = len(harvestable) - len(pending)
        state.items_skipped += skipped
        log.info("Skipping %d already-done URLs", skipped)

    log.info("Harvest: %d URLs to process (%d total discovered)", len(pending), len(harvestable))

    fetch_cfg = _make_fetch_cfg(cfg)
    guardrails = GuardrailChecker(cfg.guardrails)
    dedup = create_dedup(cfg.dedup)
    writer = ShardWriter(cfg.sharding, source=hcfg.output_source, run_id=run_id)
    rate_limiter = DomainRateLimiter(delay_s=hcfg.domain_delay_s)
    dead_letters: list[DeadLetterEntry] = []

    s3_client = None
    if cfg.s3.enabled:
        from apps.common.s3_client import get_s3_client

        s3_client = get_s3_client(cfg.s3)

    def _upload_shard(meta):
        key = shard_key(hcfg.s3_prefix, run_id, meta.filename)
        try:
            result = upload_file(s3_client, meta.path, cfg.s3.bucket, key, cfg.s3)
            if not result.skipped and cfg.s3.verify_after_upload:
                if not verify_upload(s3_client, meta.path, cfg.s3.bucket, key):
                    log.error("Verification failed for %s", key)
        except Exception:
            log.exception("S3 upload failed for %s", meta.filename)

    def _sync_state_to_s3():
        if s3_client is not None:
            try:
                upload_state(s3_client, cfg.s3.bucket, state)
                done_file = f"manifests/state/{run_id}.done.txt"
                upload_done_list(s3_client, cfg.s3.bucket, run_id, done_file)
            except Exception:
                log.exception("S3 state sync failed")

    def on_shard_closed(meta):
        append_manifest_entry(run_id, meta, source=hcfg.output_source)
        state.shards_closed += 1
        state.bytes_written += meta.bytes
        state.last_shard_name = meta.filename
        save_state(state)
        if s3_client is not None:
            _upload_shard(meta)
            state.uploaded_shards += 1
            _sync_state_to_s3()

    guardrail_hit = False

    try:
        for idx, item in enumerate(pending):
            if guardrail_hit:
                break
            if hcfg.max_items and stats.docs_kept >= hcfg.max_items:
                log.info("Reached max_items=%d", hcfg.max_items)
                break

            stats.docs_seen += 1
            state.items_done += 1
            state.current_item = item.url

            doc_json, reason = harvest_url(item, fetch_cfg, cfg, dedup, stats, rate_limiter)

            if doc_json is None:
                stats.reject_reasons[reason] += 1
                if reason.startswith("reject.dedup"):
                    stats.duplicates += 1
                if reason.startswith("reject.fetch"):
                    dead_letters.append(
                        DeadLetterEntry(
                            url=item.url,
                            url_class=item.url_class,
                            reason=reason,
                            retryable=True,
                        )
                    )
                elif reason.startswith("reject.") and "extraction" in reason:
                    dead_letters.append(
                        DeadLetterEntry(
                            url=item.url,
                            url_class=item.url_class,
                            reason=reason,
                            retryable=False,
                        )
                    )
                mark_done(run_id, item.url)
                continue

            shard_result = writer.write(doc_json)
            stats.docs_kept += 1
            stats.total_kept_chars += len(doc_json.get("text", ""))

            kept_domain = get_domain(doc_json.get("url", item.url))
            if kept_domain:
                stats.domain_kept[kept_domain] += 1

            seen_domain = get_domain(item.url)
            if seen_domain:
                stats.domain_seen[seen_domain] += 1

            mark_done(run_id, item.url)

            if shard_result is not None:
                on_shard_closed(shard_result)

            triggered, guardrail_reason = guardrails.check(state)
            if triggered:
                log.info("Guardrail triggered: %s", guardrail_reason)
                state.pause(guardrail_reason)
                guardrail_hit = True
                break

            if state.items_done % 20 == 0:
                save_state(state)
                log.info(
                    "Progress: processed=%d kept=%d remaining=%d",
                    state.items_done,
                    stats.docs_kept,
                    len(pending) - idx - 1,
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
        final_meta = writer.close()
        if final_meta is not None:
            on_shard_closed(final_meta)
        dedup.close()
        state.current_item = ""
        save_state(state)
        _sync_state_to_s3()
        save_dead_letter(dead_letters, output_dir, run_id)

    # Write enriched stats with heritage-specific sections
    _write_heritage_stats(stats, discovery_meta, dead_letters, guardrail_hit, output_dir, run_id)

    log.info(
        "Heritage harvest complete: kept=%d seen=%d dupes=%d",
        stats.docs_kept,
        stats.docs_seen,
        stats.duplicates,
    )
    return stats


def _write_heritage_stats(
    stats: RunStats,
    discovery_meta: dict,
    dead_letters: list[DeadLetterEntry],
    guardrail_hit: bool,
    output_dir: Path,
    run_id: str,
) -> None:
    """Write stats.json with discovery/harvest/quality_gates sections."""
    import json

    base = stats.to_dict()

    base["discovery"] = discovery_meta

    harvest_by_class: dict[str, int] = {}
    for reason, count in stats.reject_reasons.items():
        if reason.startswith("info."):
            harvest_by_class[reason] = count
    base["harvest"] = {
        "total_processed": stats.docs_seen,
        "kept": stats.docs_kept,
        "duplicates": stats.duplicates,
        "dead_letter_count": len(dead_letters),
        "ocr_applied": stats.reject_reasons.get("info.ocr_applied", 0),
        "lang_split_applied": stats.reject_reasons.get("info.lang_split_applied", 0),
    }

    base["quality_gates"] = {
        "guardrail_triggered": guardrail_hit,
        "lid_not_rw": stats.reject_reasons.get("reject.lid.not_rw", 0),
        "lid_low_confidence": stats.reject_reasons.get("reject.lid.low_confidence", 0),
        "pdf_extraction_failed": stats.reject_reasons.get("reject.pdf_extraction_failed", 0),
        "extraction_failed": stats.reject_reasons.get("reject.extraction_failed", 0),
        "filter_rejections": sum(
            c for r, c in stats.reject_reasons.items() if r.startswith("reject.filter.")
        ),
    }

    path = output_dir / "stats.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(base, f, indent=2)
    log.info("Stats written to %s", path)

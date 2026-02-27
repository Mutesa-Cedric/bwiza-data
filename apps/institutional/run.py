"""End-to-end institutional source runner (two-stage: discovery → harvest)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from apps.cc_miner.stats import RunStats
from apps.common.config_fingerprint import fingerprint_config
from apps.common.config_types import AppConfig
from apps.common.dedup_factory import create_dedup
from apps.common.filters.base import clear_registry
from apps.common.filters.quality import register_quality_filters
from apps.common.logging import get_logger
from apps.common.manifest import append_manifest_entry
from apps.common.run_state import RunState
from apps.common.run_state_store import load_done_set, mark_done, save_state
from apps.common.shard_writer import ShardWriter
from apps.common.url_utils import get_domain
from apps.heritage.discovery import load_discovery_index
from apps.heritage.harvest import DeadLetterEntry, harvest_url, save_dead_letter
from apps.institutional.discovery import run_discovery, save_discovery_index
from apps.institutional.source_profile import SourceProfile
from apps.targeted_crawler.rate_limit import DomainRateLimiter

log = get_logger(__name__)


def run_institutional(
    cfg: AppConfig,
    profile: SourceProfile,
    resume_run_id: str = "",
    dry_run: bool = False,
    max_pages_override: int = 0,
    max_items_override: int = 0,
) -> RunStats:
    """Run the institutional pipeline for a single source domain."""
    clear_registry()
    register_quality_filters()

    hcfg = cfg.heritage

    # Apply heritage-style overrides to shared config
    cfg.lid.min_confidence = hcfg.min_lid_confidence
    if hcfg.max_chars:
        cfg.filters.max_chars = hcfg.max_chars
    if hcfg.max_word_ngram_rep_2:
        cfg.filters.max_word_ngram_rep_2 = hcfg.max_word_ngram_rep_2
    if hcfg.max_word_ngram_rep_3:
        cfg.filters.max_word_ngram_rep_3 = hcfg.max_word_ngram_rep_3
    if hcfg.max_word_ngram_rep_4:
        cfg.filters.max_word_ngram_rep_4 = hcfg.max_word_ngram_rep_4

    if max_pages_override > 0:
        hcfg.max_listing_pages = max_pages_override
    if max_items_override > 0:
        hcfg.max_items = max_items_override

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    done_set: set[str] = set()

    if resume_run_id:
        run_id = resume_run_id
        done_set = load_done_set(run_id)
        log.info(
            "Resuming institutional run=%s [%s], %d URLs already done",
            run_id,
            profile.domain,
            len(done_set),
        )

    state = RunState(
        run_id=run_id,
        pipeline="institutional",
        source=profile.output_source,
        config_fingerprint=fingerprint_config(cfg),
    )
    state.start()
    save_state(state)

    output_dir = Path(f"outputs/institutional/{run_id}")
    output_dir.mkdir(parents=True, exist_ok=True)

    stats = RunStats()
    discovery_meta: dict = {}

    # ── STAGE 1: DISCOVERY ─────────────────────────────────
    log.info("=== STAGE 1: DISCOVERY [%s] ===", profile.domain)

    discovery_index_path = output_dir / f"{run_id}_discovery_index.jsonl"
    if discovery_index_path.exists() and resume_run_id:
        log.info("Loading saved discovery index: %s", discovery_index_path)
        discovered_urls = load_discovery_index(discovery_index_path)
        discovery_meta = {"loaded_from_cache": True, "total_urls": len(discovered_urls)}
    else:
        discovery_result = run_discovery(profile, cfg, discovery_done=done_set)
        discovered_urls = discovery_result.discovered
        save_discovery_index(discovery_result, output_dir, run_id)

        discovery_meta = {
            "domain": profile.domain,
            "pages_crawled": discovery_result.pages_crawled,
            "pages": discovery_result.news_count,
            "pdf": discovery_result.pdf_count,
            "total_urls": len(discovered_urls),
        }

    if dry_run:
        log.info(
            "DRY RUN [%s] — discovery found %d URLs (%d pages, %d PDFs)",
            profile.domain,
            len(discovered_urls),
            discovery_meta.get("pages", 0),
            discovery_meta.get("pdf", 0),
        )
        state.complete()
        save_state(state)
        _write_stats(stats, discovery_meta, profile, [], output_dir, run_id)
        return stats

    # ── STAGE 2: HARVEST ───────────────────────────────────
    log.info("=== STAGE 2: HARVEST [%s] ===", profile.domain)

    harvestable = [
        item for item in discovered_urls if item.url_class in ("page", "pdf", "document")
    ]
    pending = [item for item in harvestable if item.url not in done_set]

    state.items_total = len(harvestable)
    log.info(
        "Harvest [%s]: %d URLs to process (%d total harvestable)",
        profile.domain,
        len(pending),
        len(harvestable),
    )

    from apps.common.config_types import TargetedConfig

    fetch_cfg = TargetedConfig(
        request_timeout_s=hcfg.request_timeout_s,
        max_retries=hcfg.max_retries,
        retry_backoff_s=hcfg.retry_backoff_s,
        max_response_bytes=hcfg.max_response_bytes,
        user_agent=hcfg.user_agent,
        allowed_content_types=hcfg.allowed_content_types,
    )

    dedup = create_dedup(cfg.dedup)
    writer = ShardWriter(cfg.sharding, source=profile.output_source, run_id=run_id)
    rate_limiter = DomainRateLimiter(delay_s=hcfg.domain_delay_s)
    dead_letters: list[DeadLetterEntry] = []

    def on_shard_closed(meta):
        append_manifest_entry(run_id, meta, source=profile.output_source)
        state.shards_closed += 1
        state.bytes_written += meta.bytes
        state.last_shard_name = meta.filename
        save_state(state)

    try:
        for idx, item in enumerate(pending):
            if hcfg.max_items and stats.docs_kept >= hcfg.max_items:
                log.info("Reached max_items=%d", hcfg.max_items)
                break

            stats.docs_seen += 1
            state.items_done += 1
            state.current_item = item.url

            doc_json, reason = harvest_url(
                item,
                fetch_cfg,
                cfg,
                dedup,
                stats,
                rate_limiter,
                output_source=profile.output_source,
                source_institution=profile.name,
                license_status=profile.license_status,
                crawl_tag=f"institutional-{profile.domain}",
                rate_limit_domain=profile.domain,
            )

            if doc_json is None:
                stats.reject_reasons[reason] += 1
                if reason.startswith("reject.dedup"):
                    stats.duplicates += 1
                if reason.startswith("reject.fetch") or "extraction" in reason:
                    dead_letters.append(
                        DeadLetterEntry(
                            url=item.url,
                            url_class=item.url_class,
                            reason=reason,
                            retryable=reason.startswith("reject.fetch"),
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

            mark_done(run_id, item.url)

            if shard_result is not None:
                on_shard_closed(shard_result)

            if state.items_done % 20 == 0:
                save_state(state)
                log.info(
                    "Progress [%s]: processed=%d kept=%d remaining=%d",
                    profile.domain,
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
        save_dead_letter(dead_letters, output_dir, run_id)

    _write_stats(stats, discovery_meta, profile, dead_letters, output_dir, run_id)

    log.info(
        "Institutional [%s] complete: kept=%d seen=%d dupes=%d",
        profile.domain,
        stats.docs_kept,
        stats.docs_seen,
        stats.duplicates,
    )
    return stats


def _write_stats(
    stats: RunStats,
    discovery_meta: dict,
    profile: SourceProfile,
    dead_letters: list[DeadLetterEntry],
    output_dir: Path,
    run_id: str,
) -> None:
    """Write enriched stats.json."""
    base = stats.to_dict()
    base["source_profile"] = {
        "name": profile.name,
        "domain": profile.domain,
        "output_source": profile.output_source,
    }
    base["discovery"] = discovery_meta
    base["harvest"] = {
        "total_processed": stats.docs_seen,
        "kept": stats.docs_kept,
        "duplicates": stats.duplicates,
        "dead_letter_count": len(dead_letters),
        "ocr_applied": stats.reject_reasons.get("info.ocr_applied", 0),
        "lang_split_applied": stats.reject_reasons.get("info.lang_split_applied", 0),
    }

    path = output_dir / "stats.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(base, f, indent=2)
    log.info("Stats written to %s", path)

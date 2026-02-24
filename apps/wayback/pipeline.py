"""Wayback pipeline: HTML -> extract -> keep decision -> dedup -> Document."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from apps.cc_miner.keep import KeepDecision, decide_keep
from apps.common.config_types import AppConfig
from apps.common.hashing import hash_text
from apps.common.schema import Document
from apps.targeted_crawler.extract import extract_main_text

if TYPE_CHECKING:
    from apps.common.dedup_exact import ExactDedupStore
    from apps.common.dedup_store import DedupStore


def process_wayback_page(
    html_bytes: bytes,
    url: str,
    timestamp: str,
    cfg: AppConfig,
    dedup: DedupStore | ExactDedupStore,
) -> tuple[Document | None, KeepDecision]:
    """Extract text from an archived page, then run LID + quality + dedup.

    Returns (Document, decision) if kept, or (None, decision) if rejected.
    Reuses the same extraction and keep logic as the targeted crawler.
    """
    extracted = extract_main_text(html_bytes, url=url)
    if extracted is None:
        return None, KeepDecision(keep=False, reason="reject.extraction_failed")

    decision = decide_keep(extracted.text, cfg)
    if not decision.keep:
        return None, decision

    text_hash = hash_text(decision.normalized_text)
    is_dup, reason = dedup.is_duplicate(
        text_hash,
        decision.normalized_text,
        text_hash,
        cfg.wayback.output_source,
        "",
    )
    if is_dup:
        return None, KeepDecision(
            keep=False,
            reason=reason,
            lang=decision.lang,
            lid_score=decision.lid_score,
        )

    doc = Document(
        id=text_hash,
        text=decision.normalized_text,
        source=cfg.wayback.output_source,
        url=url,
        crawl=f"wayback-{timestamp}",
        fetched_at=datetime.now(timezone.utc).isoformat(),
        lang=decision.lang,
        lid_model="glotlid",
        lid_score=decision.lid_score,
        meta={"title": extracted.title, "wayback_timestamp": timestamp}
        if extracted.title
        else {"wayback_timestamp": timestamp},
    )

    return doc, decision

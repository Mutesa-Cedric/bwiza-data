"""Targeted crawler pipeline: extract -> keep decision -> dedup -> Document."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from apps.cc_miner.keep import KeepDecision, decide_keep
from apps.common.config_types import AppConfig
from apps.common.hashing import hash_text
from apps.common.schema import Document
from apps.targeted_crawler.extract import ExtractedDoc

if TYPE_CHECKING:
    from apps.common.dedup_exact import ExactDedupStore
    from apps.common.dedup_store import DedupStore


def process_page(
    extracted: ExtractedDoc,
    url: str,
    cfg: AppConfig,
    dedup: DedupStore | ExactDedupStore,
) -> tuple[Document | None, KeepDecision]:
    """Run the keep decision pipeline on extracted text.

    Returns (Document, decision) if kept, or (None, decision) if rejected.
    Reuses the same keep logic as CC miner (LID, filters, normalization).
    """
    decision = decide_keep(extracted.text, cfg)

    if not decision.keep:
        return None, decision

    text_hash = hash_text(decision.normalized_text)
    is_dup, reason = dedup.is_duplicate(
        text_hash,
        decision.normalized_text,
        text_hash,
        cfg.targeted.output_source,
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
        source=cfg.targeted.output_source,
        url=url,
        fetched_at=datetime.now(timezone.utc).isoformat(),
        lang=decision.lang,
        lid_model="glotlid",
        lid_score=decision.lid_score,
        meta={"title": extracted.title} if extracted.title else {},
    )

    return doc, decision

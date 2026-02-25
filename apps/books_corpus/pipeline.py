"""Books corpus pipeline: extract -> keep -> dedup -> Document."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from apps.books_corpus.seeds import BookSeed
from apps.cc_miner.keep import KeepDecision, decide_keep
from apps.common.hashing import hash_text
from apps.common.schema import Document
from apps.targeted_crawler.extract import ExtractedDoc

if TYPE_CHECKING:
    from apps.common.config_types import AppConfig
    from apps.common.dedup_exact import ExactDedupStore
    from apps.common.dedup_store import DedupStore


def process_book_doc(
    extracted: ExtractedDoc,
    url: str,
    seed: BookSeed,
    cfg: AppConfig,
    dedup: DedupStore | ExactDedupStore,
) -> tuple[Document | None, KeepDecision]:
    """Run keep + dedup pipeline for a fetched book/document."""
    decision = decide_keep(extracted.text, cfg)
    if not decision.keep:
        return None, decision

    text_hash = hash_text(decision.normalized_text)
    is_dup, reason = dedup.is_duplicate(
        text_hash,
        decision.normalized_text,
        text_hash,
        cfg.books.output_source,
        "",
    )
    if is_dup:
        return None, KeepDecision(
            keep=False,
            reason=reason,
            lang=decision.lang,
            lid_score=decision.lid_score,
        )

    meta = {
        "title": seed.title or extracted.title,
        "books_source": seed.source_name,
        "license_status": seed.license_status,
        "license_type": seed.license_type,
        "license_notes": seed.license_notes,
    }

    doc = Document(
        id=text_hash,
        text=decision.normalized_text,
        source=cfg.books.output_source,
        url=url,
        fetched_at=datetime.now(timezone.utc).isoformat(),
        lang=decision.lang,
        lid_model="glotlid",
        lid_score=decision.lid_score,
        meta=meta,
    )
    return doc, decision

"""Heritage keep/dedup pipeline: extract -> keep -> dedup -> Document."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from apps.cc_miner.keep import KeepDecision, decide_keep
from apps.common.hashing import hash_text
from apps.common.schema import Document
from apps.targeted_crawler.extract import ExtractedDoc

if TYPE_CHECKING:
    from apps.common.config_types import AppConfig
    from apps.common.dedup_exact import ExactDedupStore
    from apps.common.dedup_store import DedupStore


def process_heritage_doc(
    extracted: ExtractedDoc,
    url: str,
    url_class: str,
    section: str,
    discovery_origin: str,
    cfg: AppConfig,
    dedup: DedupStore | ExactDedupStore,
) -> tuple[Document | None, KeepDecision]:
    """Run keep + dedup pipeline for a fetched heritage document."""
    decision = decide_keep(extracted.text, cfg)
    if not decision.keep:
        return None, decision

    text_hash = hash_text(decision.normalized_text)
    is_dup, reason = dedup.is_duplicate(
        text_hash,
        decision.normalized_text,
        text_hash,
        cfg.heritage.output_source,
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
        "title": extracted.title,
        "url_class": url_class,
        "section": section,
        "discovery_origin": discovery_origin,
        "license_status": "government",
        "source_institution": "Rwanda Cultural Heritage Academy",
        "retrieval_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    }

    doc = Document(
        id=text_hash,
        text=decision.normalized_text,
        source=cfg.heritage.output_source,
        url=url,
        crawl="heritage-site",
        fetched_at=datetime.now(timezone.utc).isoformat(),
        lang=decision.lang,
        lid_model="glotlid",
        lid_score=decision.lid_score,
        meta=meta,
    )
    return doc, decision

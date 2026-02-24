"""CC index pipeline: WARC HTML -> extract -> keep decision -> dedup -> Document."""

from __future__ import annotations

from typing import TYPE_CHECKING

from apps.cc_miner.keep import KeepDecision, decide_keep
from apps.common.config_types import AppConfig
from apps.common.hashing import hash_text
from apps.common.schema import Document
from apps.targeted_crawler.extract import extract_main_text

if TYPE_CHECKING:
    from apps.common.dedup_exact import ExactDedupStore
    from apps.common.dedup_store import DedupStore


def process_warc_html(
    html_body: bytes,
    url: str,
    crawl: str,
    cfg: AppConfig,
    dedup: DedupStore | ExactDedupStore,
) -> tuple[Document | None, KeepDecision]:
    """Extract text from HTML, run LID + quality filters + dedup.

    Reuses extract_main_text from targeted_crawler and decide_keep from cc_miner.
    Returns (Document, decision) if kept, or (None, decision) if rejected.
    """
    extracted = extract_main_text(html_body, url=url)
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
        cfg.cc_index.output_source,
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
        source=cfg.cc_index.output_source,
        url=url,
        crawl=crawl,
        lang=decision.lang,
        lid_model="glotlid",
        lid_score=decision.lid_score,
        meta={"title": extracted.title} if extracted.title else {},
    )

    return doc, decision

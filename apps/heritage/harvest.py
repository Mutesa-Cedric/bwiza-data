"""Harvest pass: fetch + extract content from discovered heritage URLs.

Processes news articles (HTML) and documents (PDF) discovered in the
discovery pass. Routes through keep/dedup pipeline and writes to shards.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from apps.books_corpus.lang_split import extract_lang_sections
from apps.common.config_types import TargetedConfig
from apps.common.lid import predict_lang
from apps.common.logging import get_logger
from apps.common.ocr import ocr_pdf
from apps.heritage.discovery import DiscoveredURL
from apps.heritage.pipeline import process_heritage_doc
from apps.targeted_crawler.extract import ExtractedDoc, extract_main_text
from apps.targeted_crawler.fetch import FetchResult, fetch_url
from apps.targeted_crawler.pdf import extract_pdf_text
from apps.targeted_crawler.rate_limit import DomainRateLimiter

if TYPE_CHECKING:
    from apps.cc_miner.stats import RunStats
    from apps.common.config_types import AppConfig
    from apps.common.dedup_exact import ExactDedupStore
    from apps.common.dedup_store import DedupStore

log = get_logger(__name__)


@dataclass
class HarvestStats:
    html_kept: int = 0
    pdf_kept: int = 0
    html_rejected: int = 0
    pdf_rejected: int = 0
    fetch_errors: int = 0
    dead_letter: int = 0


@dataclass
class DeadLetterEntry:
    url: str
    url_class: str
    reason: str
    retryable: bool = True


def _make_fetch_cfg(cfg: AppConfig) -> TargetedConfig:
    hcfg = cfg.heritage
    return TargetedConfig(
        request_timeout_s=hcfg.request_timeout_s,
        max_retries=hcfg.max_retries,
        retry_backoff_s=hcfg.retry_backoff_s,
        max_response_bytes=hcfg.max_response_bytes,
        user_agent=hcfg.user_agent,
        allowed_content_types=hcfg.allowed_content_types,
    )


def _try_lang_split(
    extracted: ExtractedDoc,
    cfg: AppConfig,
    stats: RunStats,
) -> ExtractedDoc:
    """Try extracting Kinyarwanda sections from multilingual docs."""
    if len(extracted.text) < 500:
        return extracted

    lid_lang, lid_conf, _ = predict_lang(extracted.text)
    if lid_lang not in ("kin_Latn", "rw") or lid_conf < cfg.lid.min_confidence:
        kin_text = extract_lang_sections(extracted.text)
        if kin_text is not None:
            stats.reject_reasons["info.lang_split_applied"] += 1
            return ExtractedDoc(title=extracted.title, text=kin_text)

    return extracted


def harvest_url(
    item: DiscoveredURL,
    fetch_cfg: TargetedConfig,
    cfg: AppConfig,
    dedup: DedupStore | ExactDedupStore,
    stats: RunStats,
    rate_limiter: DomainRateLimiter,
) -> tuple[dict | None, str]:
    """Fetch, extract, and process a single discovered URL.

    Returns (doc_json, reject_reason). doc_json is None if rejected.
    """
    hcfg = cfg.heritage
    rate_limiter.wait_if_needed(hcfg.allowed_domain)

    result: FetchResult = fetch_url(item.url, fetch_cfg)
    if not result.ok:
        return None, f"reject.fetch.{result.error}"

    is_pdf = "application/pdf" in (result.content_type or "")

    if is_pdf:
        extracted = extract_pdf_text(
            result.content,
            url=result.final_url or item.url,
            max_pages=hcfg.pdf_max_pages,
            min_text_ratio=hcfg.pdf_min_text_ratio,
        )
    else:
        extracted = extract_main_text(
            result.content,
            url=result.final_url or item.url,
            extraction_mode=hcfg.extract_mode,
        )

    if extracted is None and is_pdf:
        # OCR fallback for scanned PDFs
        extracted = ocr_pdf(
            result.content,
            url=result.final_url or item.url,
            max_pages=hcfg.pdf_max_pages,
        )
        if extracted is not None:
            stats.reject_reasons["info.ocr_applied"] += 1

    if extracted is None:
        reason = "reject.pdf_extraction_failed" if is_pdf else "reject.extraction_failed"
        return None, reason

    # Lang-split fallback for multilingual docs
    extracted = _try_lang_split(extracted, cfg, stats)

    doc, decision = process_heritage_doc(
        extracted,
        result.final_url or item.url,
        item.url_class,
        item.section,
        item.discovery_origin,
        cfg,
        dedup,
    )

    if doc is None:
        return None, decision.reason

    return doc.to_json(), "keep"


def save_dead_letter(
    entries: list[DeadLetterEntry],
    output_dir: Path,
    run_id: str,
) -> None:
    """Persist dead-letter entries for failed extractions."""
    if not entries:
        return
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{run_id}_dead_letter.jsonl"
    with open(path, "a") as f:
        for entry in entries:
            f.write(
                json.dumps(
                    {
                        "url": entry.url,
                        "url_class": entry.url_class,
                        "reason": entry.reason,
                        "retryable": entry.retryable,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    log.info("Dead-letter: %d entries written to %s", len(entries), path)

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
from apps.common.office import extract_office_text, is_office_type, ocr_office
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
    *,
    output_source: str = "",
    source_institution: str = "Rwanda Cultural Heritage Academy",
    license_status: str = "government",
    crawl_tag: str = "heritage-site",
    rate_limit_domain: str = "",
) -> tuple[dict | None, str]:
    """Fetch, extract, and process a single discovered URL.

    Returns (doc_json, reject_reason). doc_json is None if rejected.
    """
    hcfg = cfg.heritage
    domain = rate_limit_domain or hcfg.allowed_domain
    rate_limiter.wait_if_needed(domain)

    result: FetchResult = fetch_url(item.url, fetch_cfg)
    if not result.ok:
        return None, f"reject.fetch.{result.error}"

    content_type = result.content_type or ""
    url = result.final_url or item.url
    is_pdf = "application/pdf" in content_type
    is_office = is_office_type(content_type)

    if is_pdf:
        extracted = extract_pdf_text(
            result.content,
            url=url,
            max_pages=hcfg.pdf_max_pages,
            min_text_ratio=hcfg.pdf_min_text_ratio,
        )
    elif is_office:
        extracted = extract_office_text(result.content, content_type, url=url)
    else:
        extracted = extract_main_text(
            result.content,
            url=url,
            extraction_mode=hcfg.extract_mode,
        )

    # OCR fallback for PDFs: no text layer, or garbled font encoding (zxx)
    if is_pdf and extracted is not None:
        lid_lang, lid_conf, _ = predict_lang(extracted.text[:5000])
        if lid_lang == "zxx_Latn" or (lid_conf < 0.3 and lid_lang not in ("kin_Latn", "rw")):
            log.debug(
                "PDF text is garbled (lid=%s/%.2f), falling back to OCR: %s",
                lid_lang,
                lid_conf,
                url,
            )
            extracted = None  # force OCR fallback

    if extracted is None and is_pdf:
        # OCR fallback for scanned PDFs or garbled text layer
        extracted = ocr_pdf(
            result.content,
            url=url,
            max_pages=hcfg.pdf_max_pages,
        )
        if extracted is not None:
            stats.reject_reasons["info.ocr_applied"] += 1

    if extracted is None and is_office:
        # OCR fallback for scanned office docs (image-only DOCX/PPTX)
        extracted = ocr_office(result.content, content_type, url=url)
        if extracted is not None:
            stats.reject_reasons["info.ocr_applied"] += 1

    if extracted is None:
        if is_pdf:
            reason = "reject.pdf_extraction_failed"
        elif is_office:
            reason = "reject.office_extraction_failed"
        else:
            reason = "reject.extraction_failed"
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
        output_source=output_source,
        source_institution=source_institution,
        license_status=license_status,
        crawl_tag=crawl_tag,
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

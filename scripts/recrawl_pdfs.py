"""Re-crawl PDF URLs that failed on VPS (no OCR) using local Apple Vision.

Reads a file of PDF URLs, fetches each one, tries text extraction first,
falls back to OCR, runs through LID/quality/dedup, and writes to shards.

Usage:
    python -m scripts.recrawl_pdfs /tmp/vps_recrawl_urls.txt [--dry-run] [--limit N]
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

# Allow running as `python -m scripts.recrawl_pdfs`
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from apps.books_corpus.lang_split import extract_lang_sections
from apps.cc_miner.stats import RunStats
from apps.common.config import load_config
from apps.common.dedup_factory import create_dedup
from apps.common.lid import predict_lang
from apps.common.logging import get_logger
from apps.common.ocr import ocr_pdf
from apps.common.run_state import RunState
from apps.common.run_state_store import load_done_set, mark_done, save_state
from apps.common.shard_writer import ShardWriter
from apps.targeted_crawler.extract import ExtractedDoc
from apps.targeted_crawler.fetch import FetchResult, fetch_url
from apps.targeted_crawler.pdf import extract_pdf_text
from apps.targeted_crawler.pipeline import process_page

log = get_logger(__name__)


def _try_lang_split(extracted: ExtractedDoc, cfg) -> ExtractedDoc:
    """Try extracting Kinyarwanda sections from multilingual docs."""
    if len(extracted.text) < 500:
        return extracted
    lid_lang, lid_conf, _ = predict_lang(extracted.text)
    if lid_lang not in ("kin_Latn", "rw") or lid_conf < cfg.lid.min_confidence:
        kin_text = extract_lang_sections(extracted.text)
        if kin_text is not None:
            return ExtractedDoc(title=extracted.title, text=kin_text)
    return extracted


def recrawl_pdfs(
    url_file: str,
    dry_run: bool = False,
    limit: int = 0,
) -> RunStats:
    cfg = load_config()

    # Use heritage-like settings: high timeout, large response limit
    from apps.common.config_types import TargetedConfig

    fetch_cfg = TargetedConfig(
        request_timeout_s=120,
        max_retries=2,
        retry_backoff_s=2,
        max_response_bytes=150_000_000,
        user_agent=cfg.targeted.user_agent,
        allowed_content_types=["text/html", "application/pdf", "application/xhtml+xml"],
    )

    # Load URLs
    urls = Path(url_file).read_text().strip().splitlines()
    urls = [u.strip() for u in urls if u.strip()]
    if limit:
        urls = urls[:limit]
    log.info("Loaded %d PDF URLs to recrawl", len(urls))

    # Run state
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    done_set = load_done_set(run_id)
    state = RunState(
        run_id=run_id,
        pipeline="recrawl_pdfs",
        source="targeted_web",
    )
    state.start()
    save_state(state)

    dedup = create_dedup(cfg.dedup)
    stats = RunStats()

    writer = None
    if not dry_run:
        writer = ShardWriter(cfg.sharding, source="targeted_web", run_id=run_id)

    try:
        for i, url in enumerate(urls):
            if url in done_set:
                continue

            stats.docs_seen += 1
            state.items_done += 1
            state.current_item = url

            # Fetch
            result: FetchResult = fetch_url(url, fetch_cfg)
            if not result.ok:
                stats.reject_reasons[f"reject.fetch.{result.error}"] += 1
                mark_done(run_id, url)
                continue

            effective_url = result.final_url or url

            # Text extraction
            extracted = extract_pdf_text(
                result.content,
                url=effective_url,
                max_pages=500,
                min_text_ratio=0.10,
            )

            # Check for garbled font encoding
            if extracted is not None:
                lid_lang, lid_conf, _ = predict_lang(extracted.text[:5000])
                if lid_lang == "zxx_Latn" or (
                    lid_conf < 0.3 and lid_lang not in ("kin_Latn", "rw")
                ):
                    log.debug(
                        "Garbled text (lid=%s/%.2f), forcing OCR: %s",
                        lid_lang,
                        lid_conf,
                        url,
                    )
                    extracted = None

            # OCR fallback
            if extracted is None:
                extracted = ocr_pdf(
                    result.content,
                    url=effective_url,
                    max_pages=100,
                )
                if extracted is not None:
                    stats.reject_reasons["info.ocr_applied"] += 1

            if extracted is None:
                stats.reject_reasons["reject.pdf_extraction_failed"] += 1
                mark_done(run_id, url)
                continue

            # Lang-split for multilingual docs
            extracted = _try_lang_split(extracted, cfg)

            # Pipeline: keep decision + dedup
            doc, decision = process_page(extracted, effective_url, cfg, dedup)

            if doc is None:
                stats.reject_reasons[decision.reason] += 1
                if decision.reason == "reject.dedup.exact":
                    stats.duplicates += 1
                mark_done(run_id, url)
                continue

            # Write to shard
            stats.docs_kept += 1
            stats.total_kept_chars += len(doc.text)

            if writer and not dry_run:
                writer.write(doc.to_json())

            mark_done(run_id, url)

            if (i + 1) % 25 == 0:
                save_state(state)
                log.info(
                    "Progress: %d/%d processed, kept=%d",
                    i + 1,
                    len(urls),
                    stats.docs_kept,
                )

        state.complete()
    except KeyboardInterrupt:
        log.warning("Interrupted. Flushing output.")
        state.pause("interrupted")
    except Exception as exc:
        state.fail(str(exc))
        raise
    finally:
        if writer:
            writer.close()
        dedup.close()
        state.current_item = ""
        save_state(state)
        stats.write_json("outputs/targeted", run_id)

    log.info(
        "Recrawl done: seen=%d kept=%d dupes=%d ocr=%d",
        stats.docs_seen,
        stats.docs_kept,
        stats.duplicates,
        stats.reject_reasons.get("info.ocr_applied", 0),
    )

    return stats


def main():
    parser = argparse.ArgumentParser(description="Re-crawl PDFs with OCR fallback")
    parser.add_argument("url_file", help="File with one PDF URL per line")
    parser.add_argument("--dry-run", action="store_true", help="Don't write shards")
    parser.add_argument("--limit", type=int, default=0, help="Max URLs to process")
    args = parser.parse_args()

    recrawl_pdfs(args.url_file, dry_run=args.dry_run, limit=args.limit)


if __name__ == "__main__":
    main()

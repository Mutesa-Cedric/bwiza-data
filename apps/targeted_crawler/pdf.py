"""PDF text extraction using PyMuPDF."""

from __future__ import annotations

import pymupdf

from apps.common.logging import get_logger
from apps.targeted_crawler.extract import ExtractedDoc

log = get_logger(__name__)

# Minimum characters per page to count as "has text" (not scanned).
_MIN_PAGE_CHARS = 50


def extract_pdf_text(
    pdf_bytes: bytes,
    url: str = "",
    max_pages: int = 500,
    min_text_ratio: float = 0.10,
) -> ExtractedDoc | None:
    """Extract text from a PDF document.

    Returns None if the PDF is corrupt, encrypted, exceeds *max_pages*,
    or if fewer than *min_text_ratio* of pages contain extractable text
    (likely a scanned document).
    """
    try:
        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    except Exception:
        log.debug("Failed to open PDF from %s", url)
        return None

    try:
        if doc.is_encrypted:
            log.debug("Skipping encrypted PDF: %s", url)
            return None

        if len(doc) == 0:
            return None

        if len(doc) > max_pages:
            log.debug("Skipping PDF with %d pages (max %d): %s", len(doc), max_pages, url)
            return None

        pages_with_text = 0
        page_texts: list[str] = []

        for page in doc:
            text = str(page.get_text()).strip()
            if len(text) >= _MIN_PAGE_CHARS:
                pages_with_text += 1
            if text:
                page_texts.append(text)

        text_ratio = pages_with_text / len(doc)
        if text_ratio < min_text_ratio:
            log.debug(
                "Skipping likely scanned PDF (%.0f%% pages with text): %s",
                text_ratio * 100,
                url,
            )
            return None

        full_text = "\n\n".join(page_texts)
        if not full_text.strip():
            return None

        title = doc.metadata.get("title", "") or "" if doc.metadata else ""

        return ExtractedDoc(title=title.strip(), text=full_text)
    finally:
        doc.close()

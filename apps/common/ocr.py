"""OCR fallback for scanned PDF pages using Tesseract.

Converts PDF pages to images via PyMuPDF, then runs Tesseract OCR.
Uses eng+fra languages (Latin script covers Kinyarwanda characters).
The downstream LID pipeline filters to Kinyarwanda-only text.
"""

from __future__ import annotations

import io

import pymupdf

from apps.common.logging import get_logger
from apps.targeted_crawler.extract import ExtractedDoc

log = get_logger(__name__)

# Minimum characters per page to count as "has text" from OCR.
_MIN_OCR_PAGE_CHARS = 30


def ocr_pdf(
    pdf_bytes: bytes,
    url: str = "",
    max_pages: int = 100,
    dpi: int = 300,
    lang: str = "eng+fra",
) -> ExtractedDoc | None:
    """Extract text from a scanned PDF using Tesseract OCR.

    Only call this as a fallback when ``extract_pdf_text()`` returns None
    (indicating no text layer / scanned document).

    Returns None if OCR produces no meaningful text, the PDF is
    encrypted, or exceeds *max_pages*.
    """
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        log.warning("pytesseract or Pillow not installed — OCR unavailable")
        return None

    try:
        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    except Exception:
        log.debug("OCR: failed to open PDF from %s", url)
        return None

    try:
        if doc.is_encrypted:
            log.debug("OCR: skipping encrypted PDF: %s", url)
            return None

        if len(doc) == 0:
            return None

        if len(doc) > max_pages:
            log.debug("OCR: skipping PDF with %d pages (max %d): %s", len(doc), max_pages, url)
            return None

        page_texts: list[str] = []
        pages_with_text = 0

        for page_num in range(len(doc)):
            page = doc[page_num]
            try:
                pix = page.get_pixmap(dpi=dpi)
                img = Image.open(io.BytesIO(pix.tobytes("png")))
                text = pytesseract.image_to_string(img, lang=lang).strip()
            except Exception:
                log.debug("OCR: failed on page %d of %s", page_num + 1, url)
                continue

            if len(text) >= _MIN_OCR_PAGE_CHARS:
                pages_with_text += 1
                page_texts.append(text)

        if not page_texts:
            log.debug("OCR: no text extracted from %s", url)
            return None

        full_text = "\n\n".join(page_texts)
        title = doc.metadata.get("title", "") or "" if doc.metadata else ""

        log.info(
            "OCR: extracted %d chars from %d/%d pages: %s",
            len(full_text),
            pages_with_text,
            len(doc),
            url,
        )
        return ExtractedDoc(title=title.strip(), text=full_text)
    finally:
        doc.close()

"""OCR fallback for scanned PDF pages.

On macOS, uses Apple Vision framework via ocrmac (Neural Engine accelerated,
~200ms/page). On Linux, falls back to Tesseract via pytesseract (~10-30s/page).
Renders PDF pages to images via PyMuPDF, then runs OCR.
The downstream LID pipeline filters to Kinyarwanda-only text.
"""

from __future__ import annotations

import io
import sys

import pymupdf

from apps.common.logging import get_logger
from apps.targeted_crawler.extract import ExtractedDoc

log = get_logger(__name__)

# Minimum characters per page to count as "has text" from OCR.
_MIN_OCR_PAGE_CHARS = 30


def _detect_backend() -> str:
    """Detect the best available OCR backend."""
    if sys.platform == "darwin":
        try:
            from ocrmac import ocrmac as _  # noqa: F401

            return "apple_vision"
        except ImportError:
            pass
    try:
        import pytesseract as _  # noqa: F401

        return "tesseract"
    except ImportError:
        pass
    return "none"


_OCR_BACKEND = _detect_backend()


def _ocr_page_apple_vision(img: object) -> str:
    """OCR a single PIL image using Apple Vision framework."""
    from ocrmac import ocrmac

    results = ocrmac.OCR(img, recognition_level="accurate").recognize()
    return "\n".join(text for text, _conf, _bbox in results).strip()


def _ocr_page_tesseract(img: object, lang: str) -> str:
    """OCR a single PIL image using Tesseract."""
    import pytesseract

    return pytesseract.image_to_string(img, lang=lang).strip()  # type: ignore[arg-type]


def ocr_pdf(
    pdf_bytes: bytes,
    url: str = "",
    max_pages: int = 100,
    dpi: int = 150,
    lang: str = "eng+fra",
) -> ExtractedDoc | None:
    """Extract text from a scanned PDF using OCR.

    Uses Apple Vision (macOS) or Tesseract (Linux) depending on the
    environment. Only call this as a fallback when ``extract_pdf_text()``
    returns None (indicating no text layer / scanned document).

    Returns None if OCR produces no meaningful text, the PDF is
    encrypted, or exceeds *max_pages*.
    """
    if _OCR_BACKEND == "none":
        log.warning("No OCR backend available (install ocrmac on macOS or pytesseract on Linux)")
        return None

    from PIL import Image

    log.debug("OCR: using %s backend for %s", _OCR_BACKEND, url)

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

                if _OCR_BACKEND == "apple_vision":
                    text = _ocr_page_apple_vision(img)
                else:
                    text = _ocr_page_tesseract(img, lang)
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
            "OCR[%s]: extracted %d chars from %d/%d pages: %s",
            _OCR_BACKEND,
            len(full_text),
            pages_with_text,
            len(doc),
            url,
        )
        return ExtractedDoc(title=title.strip(), text=full_text)
    finally:
        doc.close()

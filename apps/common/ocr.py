"""OCR fallback for scanned PDF pages.

On macOS, uses Apple Vision framework via ocrmac (Neural Engine accelerated,
~200ms/page). On Linux, falls back to Tesseract via pytesseract (~10-30s/page).
Renders PDF pages to images via PyMuPDF, then runs OCR.

OCR runs in a subprocess to isolate segfaults in native Vision/Tesseract code
from crashing the parent pipeline process.
"""

from __future__ import annotations

import io
import multiprocessing
import sys
import tempfile
from pathlib import Path

import pymupdf

from apps.common.logging import get_logger
from apps.targeted_crawler.extract import ExtractedDoc

log = get_logger(__name__)

# Minimum characters per page to count as "has text" from OCR.
_MIN_OCR_PAGE_CHARS = 30

# Timeout for OCR subprocess (seconds). Large PDFs can take a while.
_OCR_TIMEOUT_S = 600


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


def _ocr_worker(
    pdf_path: str,
    result_path: str,
    backend: str,
    max_pages: int,
    dpi: int,
    lang: str,
) -> None:
    """Run OCR in a child process. Writes result to a temp file.

    If this process segfaults (e.g. Apple Vision crash), only this
    child dies — the parent pipeline survives.
    """
    from PIL import Image

    try:
        doc = pymupdf.open(pdf_path)
    except Exception:
        return

    try:
        if doc.is_encrypted or len(doc) == 0 or len(doc) > max_pages:
            return

        page_texts: list[str] = []

        for page_num in range(len(doc)):
            page = doc[page_num]
            try:
                pix = page.get_pixmap(dpi=dpi)
                img = Image.open(io.BytesIO(pix.tobytes("png")))

                if backend == "apple_vision":
                    text = _ocr_page_apple_vision(img)
                else:
                    text = _ocr_page_tesseract(img, lang)
            except Exception:
                continue

            if len(text) >= _MIN_OCR_PAGE_CHARS:
                page_texts.append(text)

        if not page_texts:
            return

        full_text = "\n\n".join(page_texts)
        title = doc.metadata.get("title", "") or "" if doc.metadata else ""

        # Write result as title\0text so parent can parse it
        Path(result_path).write_text(f"{title.strip()}\0{full_text}", encoding="utf-8")
    finally:
        doc.close()


def ocr_pdf(
    pdf_bytes: bytes,
    url: str = "",
    max_pages: int = 100,
    dpi: int = 150,
    lang: str = "eng+fra",
) -> ExtractedDoc | None:
    """Extract text from a scanned PDF using OCR.

    Runs OCR in a subprocess to survive native code crashes (segfaults
    in Apple Vision / Tesseract). Returns None if OCR produces no
    meaningful text, the PDF is encrypted, exceeds *max_pages*, or the
    subprocess crashes.
    """
    if _OCR_BACKEND == "none":
        log.warning("No OCR backend available (install ocrmac on macOS or pytesseract on Linux)")
        return None

    # Quick pre-checks in parent process (no native OCR calls)
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
        n_pages = len(doc)
        if n_pages > max_pages:
            log.debug("OCR: skipping PDF with %d pages (max %d): %s", n_pages, max_pages, url)
            return None
    finally:
        doc.close()

    log.debug("OCR: using %s backend (subprocess) for %s (%d pages)", _OCR_BACKEND, url, n_pages)

    # Write PDF to temp file for subprocess access
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as pdf_tmp:
        pdf_tmp.write(pdf_bytes)
        pdf_path = pdf_tmp.name

    result_path = pdf_path + ".result"

    try:
        ctx = multiprocessing.get_context("spawn")
        proc = ctx.Process(
            target=_ocr_worker,
            args=(pdf_path, result_path, _OCR_BACKEND, max_pages, dpi, lang),
        )
        proc.start()
        proc.join(timeout=_OCR_TIMEOUT_S)

        if proc.is_alive():
            log.warning("OCR: subprocess timed out after %ds, killing: %s", _OCR_TIMEOUT_S, url)
            proc.kill()
            proc.join(timeout=10)
            return None

        if proc.exitcode != 0:
            log.warning(
                "OCR: subprocess crashed (exit=%s) for %s — skipping",
                proc.exitcode,
                url,
            )
            return None

        # Read result from temp file
        result_file = Path(result_path)
        if not result_file.exists():
            log.debug("OCR: no text extracted from %s", url)
            return None

        content = result_file.read_text(encoding="utf-8")
        title, _, full_text = content.partition("\0")

        if not full_text:
            return None

        log.info("OCR[%s]: extracted %d chars from %s", _OCR_BACKEND, len(full_text), url)
        return ExtractedDoc(title=title, text=full_text)
    finally:
        Path(pdf_path).unlink(missing_ok=True)
        Path(result_path).unlink(missing_ok=True)

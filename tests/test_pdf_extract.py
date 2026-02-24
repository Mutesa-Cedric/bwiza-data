"""Tests for PDF text extraction."""

import pymupdf

from apps.targeted_crawler.pdf import extract_pdf_text


def _make_pdf(texts: list[str], title: str = "") -> bytes:
    """Create a minimal PDF with one page per text string."""
    doc = pymupdf.open()
    if title:
        doc.set_metadata({"title": title})
    for text in texts:
        page = doc.new_page()
        if text:
            page.insert_text((72, 72), text)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


RW_TEXT = (
    "Mu Rwanda, uburezi ni ingenzi cyane ku iterambere ry'igihugu. "
    "Abanyarwanda bose bagomba kubona uburezi bwiza kandi bukwiye."
)


def test_extract_basic():
    result = extract_pdf_text(_make_pdf([RW_TEXT]), url="https://example.rw/doc.pdf")
    assert result is not None
    assert "uburezi" in result.text


def test_extract_multi_page():
    texts = [RW_TEXT, "Page two text here with enough characters to count as real content."]
    result = extract_pdf_text(_make_pdf(texts))
    assert result is not None
    assert "uburezi" in result.text
    assert "Page two" in result.text


def test_extract_title():
    result = extract_pdf_text(_make_pdf([RW_TEXT], title="My Document"))
    assert result is not None
    assert result.title == "My Document"


def test_extract_no_title():
    result = extract_pdf_text(_make_pdf([RW_TEXT]))
    assert result is not None
    assert result.title == ""


def test_extract_single_blank_page():
    result = extract_pdf_text(_make_pdf([""]))
    assert result is None


def test_extract_no_text_pages():
    result = extract_pdf_text(_make_pdf(["", "", ""]))
    assert result is None


def test_extract_corrupt_bytes():
    result = extract_pdf_text(b"not a pdf at all")
    assert result is None


def test_extract_max_pages_exceeded():
    result = extract_pdf_text(_make_pdf([RW_TEXT] * 3), max_pages=2)
    assert result is None


def test_extract_within_max_pages():
    result = extract_pdf_text(_make_pdf([RW_TEXT] * 2), max_pages=2)
    assert result is not None


def test_extract_below_text_ratio():
    texts = [RW_TEXT] + [""] * 9  # 10% pages with text
    result = extract_pdf_text(_make_pdf(texts), min_text_ratio=0.20)
    assert result is None


def test_extract_at_text_ratio_boundary():
    texts = [RW_TEXT] + [""] * 9  # 10% pages with text
    result = extract_pdf_text(_make_pdf(texts), min_text_ratio=0.10)
    assert result is not None

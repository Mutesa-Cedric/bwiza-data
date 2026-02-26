"""Tests for OCR module."""

from unittest.mock import MagicMock, patch

from apps.common.ocr import ocr_pdf


def test_ocr_returns_none_when_no_backend():
    """OCR should gracefully return None if no backend is available."""
    with patch("apps.common.ocr._OCR_BACKEND", "none"):
        result = ocr_pdf(b"fake-pdf")
        assert result is None


@patch("apps.common.ocr.pymupdf")
@patch("apps.common.ocr._OCR_BACKEND", "apple_vision")
def test_ocr_returns_none_for_encrypted_pdf(mock_pymupdf):
    doc = MagicMock()
    doc.is_encrypted = True
    mock_pymupdf.open.return_value = doc

    result = ocr_pdf(b"encrypted-pdf", url="test.pdf")
    assert result is None
    doc.close.assert_called_once()


@patch("apps.common.ocr.pymupdf")
@patch("apps.common.ocr._OCR_BACKEND", "apple_vision")
def test_ocr_returns_none_for_empty_pdf(mock_pymupdf):
    doc = MagicMock()
    doc.is_encrypted = False
    doc.__len__ = lambda self: 0
    mock_pymupdf.open.return_value = doc

    result = ocr_pdf(b"empty-pdf", url="test.pdf")
    assert result is None


@patch("apps.common.ocr.pymupdf")
@patch("apps.common.ocr._OCR_BACKEND", "apple_vision")
def test_ocr_returns_none_for_oversized_pdf(mock_pymupdf):
    doc = MagicMock()
    doc.is_encrypted = False
    doc.__len__ = lambda self: 200
    mock_pymupdf.open.return_value = doc

    result = ocr_pdf(b"big-pdf", url="test.pdf", max_pages=50)
    assert result is None
    doc.close.assert_called_once()


@patch("apps.common.ocr.pymupdf")
@patch("apps.common.ocr._OCR_BACKEND", "apple_vision")
def test_ocr_returns_none_for_invalid_pdf(mock_pymupdf):
    mock_pymupdf.open.side_effect = Exception("Invalid PDF")

    result = ocr_pdf(b"invalid", url="test.pdf")
    assert result is None

"""Tests for text normalization."""

from apps.common.normalize import normalize_text


def test_nfkc_normalization():
    # fullwidth A -> A
    assert normalize_text("\uff21") == "A"


def test_newline_normalization():
    assert normalize_text("a\r\nb\rc") == "a\nb\nc"


def test_collapse_multiple_newlines():
    assert normalize_text("a\n\n\n\nb") == "a\n\nb"


def test_collapse_whitespace():
    assert normalize_text("a   b") == "a b"


def test_strip_edges():
    assert normalize_text("  hello  ") == "hello"


def test_tabs_normalized():
    assert normalize_text("a\t\tb") == "a b"


def test_deterministic():
    text = "  Muraho\r\n\r\n\r\nneza  "
    assert normalize_text(text) == normalize_text(text)


def test_empty_string():
    assert normalize_text("") == ""


def test_preserves_case():
    assert normalize_text("Hello World") == "Hello World"

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


# --- Deep cleaning tests ---


def test_removes_zero_width_chars():
    assert normalize_text("mu\u200braho") == "muraho"
    assert normalize_text("\ufeffhello") == "hello"
    assert normalize_text("a\u200cb\u200dc") == "abc"


def test_removes_control_chars():
    assert normalize_text("hello\x00world") == "helloworld"
    assert normalize_text("a\x01b\x7fc") == "abc"
    # \n and \t are preserved
    assert normalize_text("a\nb") == "a\nb"
    assert normalize_text("a\tb") == "a b"  # \t preserved then collapsed to space


def test_decodes_html_entities():
    assert normalize_text("&amp;") == "&"
    assert normalize_text("&lt;b&gt;") == "<b>"
    assert normalize_text("&#39;") == "'"
    assert normalize_text("&quot;test&quot;") == '"test"'


def test_nbsp_decoded_and_collapsed():
    assert normalize_text("hello&nbsp;world") == "hello world"


def test_collapses_excessive_punctuation():
    assert normalize_text("wow!!!") == "wow!"
    assert normalize_text("really???") == "really?"
    assert normalize_text("a!!!!!b") == "a!b"
    # Ellipsis preserved (periods NOT collapsed)
    assert normalize_text("wait...") == "wait..."


def test_strips_repeated_separator_lines():
    sep = "\n---\n---\n---\n---"
    assert normalize_text(f"before{sep}\nafter") == "before\n\nafter"

    sep_eq = "\n===\n===\n==="
    assert normalize_text(f"a{sep_eq}\nb") == "a\n\nb"

    # Fewer than 3 separator lines are NOT stripped
    result = normalize_text("before\n---\n---\nafter")
    assert "---" in result


def test_deep_clean_combined():
    dirty = "\ufeff\x00Hello&amp;world!!!\n---\n---\n---\n---\nEnd"
    result = normalize_text(dirty)
    assert result == "Hello&world!\n\nEnd"


def test_deep_clean_preserves_kinyarwanda():
    text = "Umuryango w'Abibumbye wafashwe mu 1945. Intego yayo ni amahoro."
    assert normalize_text(text) == text


def test_idempotent():
    text = "\ufeffHello&amp;world!!!\n---\n---\n---\n---\nEnd\x00"
    once = normalize_text(text)
    twice = normalize_text(once)
    assert once == twice

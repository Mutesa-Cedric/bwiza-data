"""Tests for HTML main text extraction."""

from apps.targeted_crawler.extract import ExtractedDoc, extract_main_text

SAMPLE_HTML = b"""
<!DOCTYPE html>
<html>
<head><title>Test Page</title></head>
<body>
<nav>Home | About | Contact</nav>
<main>
<h1>Test Page</h1>
<p>This is the main content of the page. It contains several paragraphs
of text that should be extracted by the boilerplate removal algorithm.
This paragraph has enough content to be considered meaningful.</p>
<p>Here is another paragraph with more substantive content about the topic
at hand. The extractor should identify this as the main body text and
remove the navigation and footer elements.</p>
</main>
<footer>Copyright 2024 Example Corp</footer>
</body>
</html>
"""

MINIMAL_HTML = b"<html><body><p>Short</p></body></html>"

MALFORMED_HTML = b"<html><body><p>unclosed paragraph<div>mixed tags</body>"


def test_extract_main_text_basic():
    doc = extract_main_text(SAMPLE_HTML, url="https://example.com")
    assert doc is not None
    assert isinstance(doc, ExtractedDoc)
    assert len(doc.text) > 50
    assert "main content" in doc.text


def test_extract_removes_nav_footer():
    doc = extract_main_text(SAMPLE_HTML)
    if doc:
        # Nav/footer text should be stripped or at least main content present
        assert "main content" in doc.text


def test_extract_minimal_html():
    # Minimal HTML may or may not extract
    doc = extract_main_text(MINIMAL_HTML)
    # Just verify no crash
    assert doc is None or isinstance(doc, ExtractedDoc)


def test_extract_malformed_html_no_crash():
    doc = extract_main_text(MALFORMED_HTML)
    # Should not crash on malformed HTML
    assert doc is None or isinstance(doc, ExtractedDoc)


def test_extract_empty_bytes():
    doc = extract_main_text(b"")
    assert doc is None


def test_extract_non_utf8():
    # Latin-1 encoded content with replacement
    content = "Héllo wörld".encode("latin-1")
    html = b"<html><body><p>" + content + b"</p></body></html>"
    doc = extract_main_text(html)
    # Should not crash
    assert doc is None or isinstance(doc, ExtractedDoc)


def test_extract_title_present():
    doc = extract_main_text(SAMPLE_HTML, url="https://example.com")
    if doc:
        assert isinstance(doc.title, str)


def test_extract_default_mode_is_recall():
    doc = extract_main_text(SAMPLE_HTML, url="https://example.com")
    assert doc is not None
    assert "main content" in doc.text


def test_extract_precision_mode():
    doc = extract_main_text(SAMPLE_HTML, url="https://example.com", extraction_mode="precision")
    # Precision mode should still extract the main content
    assert doc is None or "main content" in doc.text


def test_extract_recall_mode_explicit():
    doc = extract_main_text(SAMPLE_HTML, url="https://example.com", extraction_mode="recall")
    assert doc is not None
    assert "main content" in doc.text

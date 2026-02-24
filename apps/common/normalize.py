"""Deterministic text normalization."""

import html as _html_mod
import re
import unicodedata

_ZERO_WIDTH = re.compile("[\u200b\u200c\u200d\ufeff]")
_CONTROL_CHARS = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\x80-\x9f]")
_MULTI_NEWLINE = re.compile(r"\n{3,}")
_MULTI_SPACE = re.compile(r"[^\S\n]+")
_EXCESSIVE_PUNCT = re.compile(r"([!?])\1+")
_SEPARATOR_LINES = re.compile(r"(\n[ \t]*[-=*_]{3,}[ \t]*){3,}")


def normalize_text(text: str) -> str:
    """Normalize text deterministically: NFKC, deep clean, whitespace, strip."""
    # Unicode normalization
    text = unicodedata.normalize("NFKC", text)
    # Remove zero-width characters
    text = _ZERO_WIDTH.sub("", text)
    # Remove control characters (preserve \n and \t)
    text = _CONTROL_CHARS.sub("", text)
    # Decode HTML entities
    text = _html_mod.unescape(text)
    # Newline normalization
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Collapse excessive punctuation (preserve ... ellipsis)
    text = _EXCESSIVE_PUNCT.sub(r"\1", text)
    # Strip repeated separator lines (3+ consecutive)
    text = _SEPARATOR_LINES.sub("\n\n", text)
    # Collapse multiple newlines
    text = _MULTI_NEWLINE.sub("\n\n", text)
    # Collapse horizontal whitespace
    text = _MULTI_SPACE.sub(" ", text)
    # Strip edges
    text = text.strip()
    return text

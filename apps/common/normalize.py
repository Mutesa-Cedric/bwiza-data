"""Deterministic text normalization."""

import re
import unicodedata

_MULTI_NEWLINE = re.compile(r"\n{3,}")
_MULTI_SPACE = re.compile(r"[^\S\n]+")


def normalize_text(text: str) -> str:
    """Normalize text deterministically: NFKC, newlines, whitespace, strip."""
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _MULTI_NEWLINE.sub("\n\n", text)
    text = _MULTI_SPACE.sub(" ", text)
    text = text.strip()
    return text

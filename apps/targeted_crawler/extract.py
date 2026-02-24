"""HTML main text extraction with boilerplate removal."""

import re
from dataclasses import dataclass
from typing import Any

import trafilatura

from apps.common.logging import get_logger

log = get_logger(__name__)

# Boilerplate patterns commonly left by trafilatura in crawled pages.
_BOILERPLATE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^Sign in to your account$", re.IGNORECASE),
    re.compile(r"^Log ?in$", re.IGNORECASE),
    re.compile(r"^Sign ?up$", re.IGNORECASE),
    re.compile(r"^Subscribe( now)?$", re.IGNORECASE),
    re.compile(r"^Share this", re.IGNORECASE),
    re.compile(r"^Cookie", re.IGNORECASE),
    re.compile(r"^Accept (all )?cookies", re.IGNORECASE),
    re.compile(r"^Privacy policy$", re.IGNORECASE),
    re.compile(r"^Terms (of|and) ", re.IGNORECASE),
    re.compile(r"^All rights reserved\.?$", re.IGNORECASE),
    re.compile(r"^Copyright ©", re.IGNORECASE),
    re.compile(r"^Powered by ", re.IGNORECASE),
]


@dataclass
class ExtractedDoc:
    title: str
    text: str


def _strip_boilerplate_lines(text: str) -> str:
    """Remove lines that match known boilerplate patterns."""
    lines = text.split("\n")
    cleaned = []
    for line in lines:
        stripped = line.strip()
        if stripped and any(pat.match(stripped) for pat in _BOILERPLATE_PATTERNS):
            continue
        cleaned.append(line)
    return "\n".join(cleaned).strip()


def extract_main_text(html_bytes: bytes, url: str = "") -> ExtractedDoc | None:
    """Extract main text content from HTML, removing boilerplate.

    Returns None if no meaningful text could be extracted.
    """
    try:
        html_str = html_bytes.decode("utf-8", errors="replace")
    except Exception:
        log.debug("Failed to decode HTML from %s", url)
        return None

    result: Any = trafilatura.bare_extraction(
        html_str,
        include_comments=False,
        include_tables=True,
        no_fallback=False,
        favor_recall=True,
        url=url or None,
    )

    if not result:
        return None

    result_dict: dict[str, Any] = result.as_dict() if hasattr(result, "as_dict") else result

    text = result_dict.get("text", "")
    if not text or not text.strip():
        return None

    text = _strip_boilerplate_lines(text)
    if not text:
        return None

    title = result_dict.get("title", "") or ""
    return ExtractedDoc(title=title.strip(), text=text)

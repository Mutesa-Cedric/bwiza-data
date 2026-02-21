"""HTML main text extraction with boilerplate removal."""

from dataclasses import dataclass

import trafilatura

from apps.common.logging import get_logger

log = get_logger(__name__)


@dataclass
class ExtractedDoc:
    title: str
    text: str


def extract_main_text(html_bytes: bytes, url: str = "") -> ExtractedDoc | None:
    """Extract main text content from HTML, removing boilerplate.

    Returns None if no meaningful text could be extracted.
    """
    try:
        html_str = html_bytes.decode("utf-8", errors="replace")
    except Exception:
        log.debug("Failed to decode HTML from %s", url)
        return None

    result = trafilatura.bare_extraction(
        html_str,
        include_comments=False,
        include_tables=True,
        no_fallback=False,
        favor_recall=True,
        url=url or None,
    )

    if not result:
        return None

    result_dict = result.as_dict() if hasattr(result, "as_dict") else result

    text = result_dict.get("text", "")
    if not text or not text.strip():
        return None

    title = result_dict.get("title", "") or ""
    return ExtractedDoc(title=title.strip(), text=text.strip())

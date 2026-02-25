"""Extract target-language sections from multilingual documents.

Designed for trilingual gazette PDFs (Kinyarwanda / English / French)
where each law appears in all three languages sequentially.  Splits text
into blocks, LIDs each block, and reassembles only the target-language
blocks.
"""

from __future__ import annotations

import re

from apps.common.lid import predict_lang
from apps.common.logging import get_logger

log = get_logger(__name__)


def extract_lang_sections(
    text: str,
    target_lang: str = "kin_Latn",
    block_size: int = 2000,
    min_confidence: float = 0.80,
    min_result_chars: int = 200,
) -> str | None:
    """Extract sections matching *target_lang* from a multilingual document.

    Splits *text* into blocks of approximately *block_size* characters
    (on paragraph boundaries), runs LID on each block, and keeps blocks
    where the detected language matches *target_lang* with at least
    *min_confidence*.

    Returns the joined Kinyarwanda text, or ``None`` if fewer than
    *min_result_chars* characters were found.
    """
    paragraphs = re.split(r"\n\s*\n", text)

    # Merge consecutive paragraphs into ~block_size char blocks
    blocks: list[str] = []
    current: list[str] = []
    current_len = 0

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        current.append(para)
        current_len += len(para)
        if current_len >= block_size:
            blocks.append("\n\n".join(current))
            current = []
            current_len = 0

    if current:
        blocks.append("\n\n".join(current))

    # LID each block and keep target-language matches
    kept: list[str] = []
    kept_chars = 0

    for block in blocks:
        if len(block) < 50:
            continue
        lang, conf, _ = predict_lang(block)
        if lang == target_lang and conf >= min_confidence:
            kept.append(block)
            kept_chars += len(block)

    if kept_chars < min_result_chars:
        log.debug(
            "lang_split: only %d chars of %s found (need %d)",
            kept_chars,
            target_lang,
            min_result_chars,
        )
        return None

    result = "\n\n".join(kept)
    log.info(
        "lang_split: extracted %d/%d chars (%d blocks) as %s",
        len(result),
        len(text),
        len(kept),
        target_lang,
    )
    return result

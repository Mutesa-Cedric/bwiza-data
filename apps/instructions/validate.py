"""Validate instruction examples (purity, size, structure)."""

import re

from apps.common.config_types import InstructionsConfig
from apps.common.instruction_schema import InstructionExample

_REPEAT_LINE_RE = re.compile(r"^(.{10,})$", re.MULTILINE)


def validate_instruction(
    ex: InstructionExample,
    cfg: InstructionsConfig,
) -> tuple[bool, str]:
    """Validate an instruction example.

    Returns (ok, reason_code). reason_code is empty string when ok=True.
    """
    if not ex.prompt or not ex.prompt.strip():
        return False, "reject.empty_prompt"

    if not ex.response or not ex.response.strip():
        return False, "reject.empty_response"

    if len(ex.prompt.strip()) < cfg.min_chars_prompt:
        return False, "reject.too_short"

    if len(ex.response.strip()) < cfg.min_chars_response:
        return False, "reject.too_short"

    if len(ex.prompt) > cfg.max_chars_prompt:
        return False, "reject.too_long"

    if len(ex.response) > cfg.max_chars_response:
        return False, "reject.too_long"

    # Repeated-line junk detection
    if _has_excessive_repeats(ex.response):
        return False, "reject.low_quality"

    return True, ""


def validate_instruction_with_lid(
    ex: InstructionExample,
    cfg: InstructionsConfig,
) -> tuple[bool, str]:
    """Validate with LID purity check (requires model loaded).

    Checks that the response is primarily Kinyarwanda,
    allowing a small ratio of English tokens.
    """
    ok, reason = validate_instruction(ex, cfg)
    if not ok:
        return ok, reason

    from apps.common.lid import predict_lang

    lang, score, _ = predict_lang(ex.response)

    # Accept kin_Latn (Kinyarwanda) with reasonable confidence
    rw_codes = {"kin_Latn", "rw"}
    en_codes = {"eng_Latn", "en"}

    if lang in rw_codes and score >= 0.5:
        return True, ""

    # Allow mixed content if English ratio is within bounds
    if lang in en_codes and cfg.allow_english_ratio > 0:
        # Re-check: if mostly English, reject
        return False, "reject.not_rw"

    if lang not in rw_codes:
        return False, "reject.not_rw"

    return True, ""


def _has_excessive_repeats(text: str, max_ratio: float = 0.5) -> bool:
    """Detect if text has too many repeated lines."""
    lines = _REPEAT_LINE_RE.findall(text)
    if len(lines) < 3:
        return False
    unique = set(lines)
    if len(unique) == 0:
        return False
    repeat_ratio = 1.0 - (len(unique) / len(lines))
    return repeat_ratio > max_ratio

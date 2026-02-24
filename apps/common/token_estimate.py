"""Rough token estimation helper."""

# Text fields to consider for token estimation across all schemas.
_TEXT_FIELDS = ("text", "rw_text", "en_text", "prompt", "response")

# Calibrated on Qwen3-8B tokenizer against Kinyarwanda corpus (Gate G2).
# Kinyarwanda is agglutinative — BPE over-splits, yielding ~2.55 chars/token
# vs ~4.0 for English. Previous constant of 4.0 underestimated by ~57%.
# Re-calibrate after switching tokenizers (see scripts/gate_token_calibration.py).
CHARS_PER_TOKEN = 2.55


def estimate_tokens(text: str) -> int:
    """Approximate token count from character length."""
    return int(len(text) / CHARS_PER_TOKEN)


def estimate_tokens_from_doc(doc: dict) -> int:
    """Estimate tokens from a document dict, handling all schemas."""
    total_chars = 0
    for key in _TEXT_FIELDS:
        if key in doc and isinstance(doc[key], str):
            total_chars += len(doc[key])
    if total_chars == 0:
        for v in doc.values():
            if isinstance(v, str):
                total_chars += len(v)
    return int(total_chars / CHARS_PER_TOKEN)

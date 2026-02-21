"""Rough token estimation helper."""

# Text fields to consider for token estimation across all schemas.
_TEXT_FIELDS = ("text", "rw_text", "en_text", "prompt", "response")


def estimate_tokens(text: str) -> int:
    """Approximate token count from character length."""
    return int(len(text) / 4)


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
    return int(total_chars / 4)

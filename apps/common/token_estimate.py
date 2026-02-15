"""Rough token estimation helper."""


def estimate_tokens(text: str) -> int:
    """Approximate token count from character length."""
    return int(len(text) / 4)

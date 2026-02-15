"""Stable SHA256 hashing for deduplication."""

import hashlib


def hash_text(text: str) -> str:
    """SHA256 hex digest of UTF-8 encoded text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

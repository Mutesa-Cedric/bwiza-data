"""Tests for stable hashing."""

from apps.common.hashing import hash_text


def test_hash_deterministic():
    assert hash_text("hello") == hash_text("hello")


def test_hash_different_for_different_input():
    assert hash_text("hello") != hash_text("world")


def test_hash_is_hex_sha256():
    h = hash_text("test")
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)


def test_hash_known_value():
    import hashlib
    expected = hashlib.sha256(b"muraho").hexdigest()
    assert hash_text("muraho") == expected

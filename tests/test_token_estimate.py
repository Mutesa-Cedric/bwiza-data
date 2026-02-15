"""Tests for token estimation."""

from apps.common.token_estimate import estimate_tokens


def test_basic_estimate():
    assert estimate_tokens("a" * 400) == 100


def test_empty():
    assert estimate_tokens("") == 0


def test_deterministic():
    text = "Muraho neza" * 10
    assert estimate_tokens(text) == estimate_tokens(text)

"""Tests for token estimation."""

from apps.common.token_estimate import (
    CHARS_PER_TOKEN,
    estimate_tokens,
    estimate_tokens_from_doc,
)


def test_basic_estimate():
    assert estimate_tokens("a" * 400) == int(400 / CHARS_PER_TOKEN)


def test_empty():
    assert estimate_tokens("") == 0


def test_deterministic():
    text = "Muraho neza" * 10
    assert estimate_tokens(text) == estimate_tokens(text)


def test_from_doc_cc_schema():
    doc = {"id": "1", "text": "a" * 400, "source": "cc"}
    assert estimate_tokens_from_doc(doc) == int(400 / CHARS_PER_TOKEN)


def test_from_doc_parallel_schema():
    doc = {"id": "1", "rw_text": "a" * 200, "en_text": "b" * 200}
    assert estimate_tokens_from_doc(doc) == int(400 / CHARS_PER_TOKEN)


def test_from_doc_instruction_schema():
    doc = {"id": "1", "prompt": "a" * 100, "response": "b" * 300}
    assert estimate_tokens_from_doc(doc) == int(400 / CHARS_PER_TOKEN)


def test_from_doc_empty():
    assert estimate_tokens_from_doc({}) == 0


def test_from_doc_fallback_unknown_fields():
    doc = {"custom_field": "a" * 400}
    assert estimate_tokens_from_doc(doc) == int(400 / CHARS_PER_TOKEN)

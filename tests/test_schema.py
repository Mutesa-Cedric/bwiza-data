"""Tests for Document schema."""

import json

from apps.common.schema import Document


def test_document_to_json():
    doc = Document(
        id="abc123",
        text="Muraho neza",
        source="commoncrawl",
        lang="rw",
        lid_model="glotlid",
        lid_score=0.95,
        url="https://example.rw/page",
        crawl="CC-MAIN-2025-01",
    )
    j = doc.to_json()
    assert j["id"] == "abc123"
    assert j["text"] == "Muraho neza"
    assert j["source"] == "commoncrawl"
    assert j["lang"] == "rw"
    assert j["lid_score"] == 0.95
    assert j["url"] == "https://example.rw/page"
    assert j["crawl"] == "CC-MAIN-2025-01"
    # Must be JSON serializable
    json.dumps(j)


def test_document_optional_fields_default():
    doc = Document(id="x", text="t", source="s", lang="rw", lid_model="m", lid_score=0.9)
    j = doc.to_json()
    assert j["url"] is None
    assert j["crawl"] is None
    assert j["fetched_at"] is None
    assert j["meta"] == {}
    json.dumps(j)


def test_document_with_meta():
    doc = Document(
        id="x",
        text="t",
        source="s",
        lang="rw",
        lid_model="m",
        lid_score=0.9,
        meta={"domain": "example.rw"},
    )
    assert doc.to_json()["meta"]["domain"] == "example.rw"

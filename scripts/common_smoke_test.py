#!/usr/bin/env python3
"""Smoke test exercising all common modules."""

import sys


def main() -> int:
    from apps.common.config import load_config
    from apps.common.dedup_exact import ExactDedupStore
    from apps.common.filters.base import clear_registry, run_filters
    from apps.common.filters.quality import register_quality_filters
    from apps.common.hashing import hash_text
    from apps.common.logging import get_logger, setup_logging
    from apps.common.normalize import normalize_text
    from apps.common.schema import Document
    from apps.common.url_utils import get_domain

    cfg = load_config()
    setup_logging(cfg.logging.level)
    log = get_logger("common_smoke_test")

    # Config
    log.info("Config loaded OK")

    # Normalize
    result = normalize_text("  hello\r\n\r\n\r\nworld  ")
    assert result == "hello\n\nworld", f"Normalize failed: {result!r}"
    log.info("Normalize OK")

    # Hashing
    h = hash_text("test")
    assert len(h) == 64
    log.info("Hashing OK")

    # Dedup
    store = ExactDedupStore()
    assert store.check_and_add(h) is False
    assert store.check_and_add(h) is True
    log.info("Dedup OK")

    # URL utils
    assert get_domain("https://www.example.com/path") == "example.com"
    log.info("URL utils OK")

    # Filters
    clear_registry()
    register_quality_filters()
    text = "Muraho neza. " * 50
    passed, reasons = run_filters(text, cfg)
    assert passed is True, f"Filters failed: {reasons}"
    log.info("Filters OK")

    # Schema
    doc = Document(
        id=h,
        text=text,
        source="test",
        lang="rw",
        lid_model="test",
        lid_score=0.95,
    )
    j = doc.to_json()
    assert j["id"] == h
    log.info("Schema OK")

    log.info("All common smoke tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Tests for targeted crawler seed loader."""

import tempfile

import pytest

from apps.targeted_crawler.seeds import (
    SeedEntry,
    canonical_domain,
    domain_set_from_seeds,
    extraction_mode_map_from_seeds,
    load_seeds,
    path_prefix_map_from_seeds,
)


def test_canonical_domain_strips_www():
    assert canonical_domain("www.Example.COM") == "example.com"


def test_canonical_domain_lowercases():
    assert canonical_domain("IGIHE.COM") == "igihe.com"


def test_canonical_domain_strips_whitespace():
    assert canonical_domain("  umuseke.rw  ") == "umuseke.rw"


def test_load_seeds_bare_domains():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("umuseke.rw\nigihe.com\n")
        f.flush()
        seeds = load_seeds(f.name)

    assert len(seeds) == 2
    assert seeds[0].start_url == "https://umuseke.rw/"
    assert seeds[0].domain == "umuseke.rw"
    assert seeds[0].path_prefix == ""
    assert seeds[0].extraction_mode == "recall"
    assert seeds[1].domain == "igihe.com"


def test_load_seeds_urls():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("https://rw.wikipedia.org/wiki/Main_Page\n")
        f.flush()
        seeds = load_seeds(f.name)

    assert len(seeds) == 1
    assert seeds[0].start_url == "https://rw.wikipedia.org/wiki/Main_Page"
    assert seeds[0].domain == "rw.wikipedia.org"
    assert seeds[0].extraction_mode == "recall"


def test_load_seeds_ignores_comments_and_blanks():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("# This is a comment\n\numuseke.rw\n\n# Another comment\n")
        f.flush()
        seeds = load_seeds(f.name)

    assert len(seeds) == 1
    assert seeds[0].domain == "umuseke.rw"


def test_load_seeds_deduplicates():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("umuseke.rw\nwww.umuseke.rw\n")
        f.flush()
        seeds = load_seeds(f.name)

    assert len(seeds) == 1


def test_load_seeds_missing_file():
    with pytest.raises(FileNotFoundError):
        load_seeds("/nonexistent/seeds.txt")


def test_load_seeds_www_stripped():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("www.igire.rw\n")
        f.flush()
        seeds = load_seeds(f.name)

    assert seeds[0].start_url == "https://igire.rw/"
    assert seeds[0].domain == "igire.rw"


def test_domain_set_from_seeds():
    seeds = [
        SeedEntry("https://umuseke.rw/", "umuseke.rw", ""),
        SeedEntry("https://igihe.com/", "igihe.com", ""),
    ]
    assert domain_set_from_seeds(seeds) == {"umuseke.rw", "igihe.com"}


def test_load_actual_seeds_file():
    seeds = load_seeds("configs/targeted_domains.txt")
    assert len(seeds) >= 5
    domains = domain_set_from_seeds(seeds)
    assert "umuseke.rw" in domains
    assert "igihe.com" in domains


def test_load_seeds_path_prefix():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("who.int/rw\nbible.com/languages/kin\nigihe.com\n")
        f.flush()
        seeds = load_seeds(f.name)

    assert len(seeds) == 3
    assert seeds[0].start_url == "https://who.int/rw"
    assert seeds[0].domain == "who.int"
    assert seeds[0].path_prefix == "/rw"
    assert seeds[1].start_url == "https://bible.com/languages/kin"
    assert seeds[1].path_prefix == "/languages/kin"
    assert seeds[2].domain == "igihe.com"
    assert seeds[2].path_prefix == ""


def test_path_prefix_map_from_seeds():
    seeds = [
        SeedEntry("https://who.int/rw", "who.int", "/rw"),
        SeedEntry("https://igihe.com/", "igihe.com", ""),
        SeedEntry("https://bible.com/languages/kin", "bible.com", "/languages/kin"),
    ]
    prefixes = path_prefix_map_from_seeds(seeds)
    assert prefixes == {"who.int": "/rw", "bible.com": "/languages/kin"}
    assert "igihe.com" not in prefixes


# --- Extraction mode tests ---


def test_load_seeds_extraction_mode_precision():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("igihe.com precision\numuseke.rw recall\n")
        f.flush()
        seeds = load_seeds(f.name)

    assert seeds[0].domain == "igihe.com"
    assert seeds[0].extraction_mode == "precision"
    assert seeds[1].domain == "umuseke.rw"
    assert seeds[1].extraction_mode == "recall"


def test_load_seeds_extraction_mode_default():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("gov.rw\n")
        f.flush()
        seeds = load_seeds(f.name)

    assert seeds[0].extraction_mode == "recall"


def test_load_seeds_extraction_mode_with_path_prefix():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("who.int/rw precision\nbible.com/languages/kin\n")
        f.flush()
        seeds = load_seeds(f.name)

    assert seeds[0].domain == "who.int"
    assert seeds[0].path_prefix == "/rw"
    assert seeds[0].extraction_mode == "precision"
    assert seeds[1].domain == "bible.com"
    assert seeds[1].extraction_mode == "recall"


def test_load_seeds_invalid_extraction_mode():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("igihe.com turbo\n")
        f.flush()
        with pytest.raises(ValueError, match="Invalid extraction mode"):
            load_seeds(f.name)


def test_extraction_mode_map_from_seeds():
    seeds = [
        SeedEntry("https://igihe.com/", "igihe.com", "", "precision"),
        SeedEntry("https://gov.rw/", "gov.rw", "", "recall"),
        SeedEntry("https://umuseke.rw/", "umuseke.rw", "", "precision"),
    ]
    mode_map = extraction_mode_map_from_seeds(seeds)
    assert mode_map == {"igihe.com": "precision", "umuseke.rw": "precision"}
    assert "gov.rw" not in mode_map


def test_load_seeds_case_insensitive_mode():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("igihe.com PRECISION\n")
        f.flush()
        seeds = load_seeds(f.name)

    assert seeds[0].extraction_mode == "precision"

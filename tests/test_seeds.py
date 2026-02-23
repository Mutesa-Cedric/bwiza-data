"""Tests for targeted crawler seed loader."""

import tempfile

import pytest

from apps.targeted_crawler.seeds import (
    canonical_domain,
    domain_set_from_seeds,
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
    assert seeds[0] == ("https://umuseke.rw/", "umuseke.rw", "")
    assert seeds[1] == ("https://igihe.com/", "igihe.com", "")


def test_load_seeds_urls():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("https://rw.wikipedia.org/wiki/Main_Page\n")
        f.flush()
        seeds = load_seeds(f.name)

    assert len(seeds) == 1
    assert seeds[0] == ("https://rw.wikipedia.org/wiki/Main_Page", "rw.wikipedia.org", "")


def test_load_seeds_ignores_comments_and_blanks():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("# This is a comment\n\numuseke.rw\n\n# Another comment\n")
        f.flush()
        seeds = load_seeds(f.name)

    assert len(seeds) == 1
    assert seeds[0][1] == "umuseke.rw"


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

    assert seeds[0] == ("https://igire.rw/", "igire.rw", "")


def test_domain_set_from_seeds():
    seeds = [
        ("https://umuseke.rw/", "umuseke.rw", ""),
        ("https://igihe.com/", "igihe.com", ""),
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
    assert seeds[0] == ("https://who.int/rw", "who.int", "/rw")
    assert seeds[1] == ("https://bible.com/languages/kin", "bible.com", "/languages/kin")
    assert seeds[2] == ("https://igihe.com/", "igihe.com", "")


def test_path_prefix_map_from_seeds():
    seeds = [
        ("https://who.int/rw", "who.int", "/rw"),
        ("https://igihe.com/", "igihe.com", ""),
        ("https://bible.com/languages/kin", "bible.com", "/languages/kin"),
    ]
    prefixes = path_prefix_map_from_seeds(seeds)
    assert prefixes == {"who.int": "/rw", "bible.com": "/languages/kin"}
    assert "igihe.com" not in prefixes

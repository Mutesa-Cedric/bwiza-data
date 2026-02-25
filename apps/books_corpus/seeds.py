"""Seed loader for book/document URLs with license audit metadata."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from apps.targeted_crawler.seeds import canonical_domain


@dataclass
class BookSeed:
    """Single source entry for books/document ingestion."""

    url: str
    title: str = ""
    source_name: str = ""
    license_status: str = "unknown"
    license_type: str = "unknown"
    license_notes: str = ""


def _normalize_url(raw: str) -> str:
    value = raw.strip()
    if not value:
        return ""
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return ""
    return value


def _parse_line(line: str) -> BookSeed | None:
    # Preferred format is tab-separated. Fallback accepts URL-only lines.
    parts = [p.strip() for p in line.split("\t")]
    if len(parts) == 1:
        url = _normalize_url(parts[0])
        if not url:
            return None
        return BookSeed(url=url)

    url = _normalize_url(parts[0])
    if not url:
        return None

    return BookSeed(
        url=url,
        title=parts[1] if len(parts) > 1 else "",
        source_name=parts[2] if len(parts) > 2 else "",
        license_status=(parts[3] if len(parts) > 3 else "unknown") or "unknown",
        license_type=(parts[4] if len(parts) > 4 else "unknown") or "unknown",
        license_notes=parts[5] if len(parts) > 5 else "",
    )


def load_book_seeds(path: str | Path) -> list[BookSeed]:
    """Load book seeds from a text file (tab-delimited or URL-only)."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Books seeds file not found: {p}")

    seeds: list[BookSeed] = []
    seen_urls: set[str] = set()

    for raw_line in p.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        seed = _parse_line(line)
        if seed is None or seed.url in seen_urls:
            continue

        seen_urls.add(seed.url)
        seeds.append(seed)

    return seeds


def domain_for_seed(seed: BookSeed) -> str:
    """Return canonical domain for a seed URL."""
    parsed = urlparse(seed.url)
    return canonical_domain(parsed.hostname or "")

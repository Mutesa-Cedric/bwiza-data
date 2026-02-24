"""Seed loader: reads allowlisted domains/URLs and produces start URLs."""

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

_VALID_MODES = {"recall", "precision"}


@dataclass
class SeedEntry:
    """A single seed domain with crawling parameters."""

    start_url: str
    domain: str
    path_prefix: str
    extraction_mode: str = "recall"


def canonical_domain(raw: str) -> str:
    """Normalize a domain: lowercase, strip www. prefix."""
    d = raw.lower().strip()
    if d.startswith("www."):
        d = d[4:]
    return d


def load_seeds(path: str | Path) -> list[SeedEntry]:
    """Load seeds file and return list of SeedEntry.

    File format: one entry per line.  Lines starting with '#' and blank
    lines are ignored.

    Each line is: ``domain_or_url [extraction_mode]``

    * A bare domain generates ``https://<domain>/``.
    * ``who.int/rw`` restricts crawling to the ``/rw`` path prefix.
    * An optional trailing token ``precision`` or ``recall`` sets the
      per-domain trafilatura extraction mode (default: ``recall``).
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Seeds file not found: {path}")

    results: list[SeedEntry] = []
    seen_domains: set[str] = set()

    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        # Split off optional extraction mode token
        parts = line.split()
        entry = parts[0]
        extraction_mode = "recall"
        if len(parts) >= 2:
            mode_token = parts[1].lower()
            if mode_token not in _VALID_MODES:
                raise ValueError(
                    f"Invalid extraction mode {parts[1]!r} for {entry!r}. "
                    f"Must be one of {_VALID_MODES}"
                )
            extraction_mode = mode_token

        if entry.startswith("http://") or entry.startswith("https://"):
            parsed = urlparse(entry)
            domain = canonical_domain(parsed.hostname or "")
            url = entry
            path_prefix = ""
        else:
            # Check for domain/path format (e.g. who.int/rw)
            slash_idx = entry.find("/")
            if slash_idx > 0:
                raw_domain = entry[:slash_idx]
                path_prefix = entry[slash_idx:]  # includes leading /
                domain = canonical_domain(raw_domain)
                url = f"https://{domain}{path_prefix}"
            else:
                domain = canonical_domain(entry)
                url = f"https://{domain}/"
                path_prefix = ""

        if not domain:
            continue
        if domain in seen_domains:
            continue
        seen_domains.add(domain)
        results.append(SeedEntry(url, domain, path_prefix, extraction_mode))

    return results


def domain_set_from_seeds(seeds: list[SeedEntry]) -> set[str]:
    """Extract the set of canonical domains from loaded seeds."""
    return {s.domain for s in seeds}


def path_prefix_map_from_seeds(seeds: list[SeedEntry]) -> dict[str, str]:
    """Extract domain -> path_prefix mapping (only for domains with a prefix)."""
    return {s.domain: s.path_prefix for s in seeds if s.path_prefix}


def extraction_mode_map_from_seeds(seeds: list[SeedEntry]) -> dict[str, str]:
    """Extract domain -> extraction_mode mapping (only for non-default modes)."""
    return {s.domain: s.extraction_mode for s in seeds if s.extraction_mode != "recall"}

"""Seed loader: reads allowlisted domains/URLs and produces start URLs."""

from pathlib import Path
from urllib.parse import urlparse


def canonical_domain(raw: str) -> str:
    """Normalize a domain: lowercase, strip www. prefix."""
    d = raw.lower().strip()
    if d.startswith("www."):
        d = d[4:]
    return d


def load_seeds(path: str | Path) -> list[tuple[str, str]]:
    """Load seeds file and return list of (start_url, canonical_domain).

    File format: one domain or URL per line.
    Lines starting with '#' and blank lines are ignored.
    If a bare domain is given, https://<domain>/ is generated.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Seeds file not found: {path}")

    results: list[tuple[str, str]] = []
    seen_domains: set[str] = set()

    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        if line.startswith("http://") or line.startswith("https://"):
            parsed = urlparse(line)
            domain = canonical_domain(parsed.hostname or "")
            url = line
        else:
            domain = canonical_domain(line)
            url = f"https://{domain}/"

        if not domain:
            continue
        if domain in seen_domains:
            continue
        seen_domains.add(domain)
        results.append((url, domain))

    return results


def domain_set_from_seeds(seeds: list[tuple[str, str]]) -> set[str]:
    """Extract the set of canonical domains from loaded seeds."""
    return {domain for _, domain in seeds}

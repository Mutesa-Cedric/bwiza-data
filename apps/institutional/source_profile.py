"""Source profile definitions for institutional domains."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from apps.common.logging import get_logger

log = get_logger(__name__)

_DEFAULT_PROFILES_PATH = "configs/institutional_sources.yaml"


@dataclass
class SourceProfile:
    name: str
    domain: str
    output_source: str
    license_status: str
    seeds: list[str] = field(default_factory=list)
    excluded_path_prefixes: list[str] = field(default_factory=lambda: ["/en/", "/fr/"])


def load_profiles(path: str | Path = _DEFAULT_PROFILES_PATH) -> list[SourceProfile]:
    """Load source profiles from YAML config."""
    path = Path(path)
    if not path.exists():
        log.warning("Profiles file not found: %s", path)
        return []

    with open(path) as f:
        data = yaml.safe_load(f)

    profiles = []
    for entry in data.get("sources", []):
        profiles.append(
            SourceProfile(
                name=entry["name"],
                domain=entry["domain"],
                output_source=entry["output_source"],
                license_status=entry.get("license_status", "government"),
                seeds=entry.get("seeds", []),
                excluded_path_prefixes=entry.get("excluded_path_prefixes", ["/en/", "/fr/"]),
            )
        )

    log.info("Loaded %d source profiles from %s", len(profiles), path)
    return profiles


def get_profile(domain: str, path: str | Path = _DEFAULT_PROFILES_PATH) -> SourceProfile | None:
    """Load a single profile by domain name."""
    for profile in load_profiles(path):
        if profile.domain == domain:
            return profile
    return None

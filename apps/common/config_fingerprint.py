"""Deterministic config fingerprinting."""

import hashlib
import json
from dataclasses import asdict

from apps.common.config_types import AppConfig


def fingerprint_config(cfg: AppConfig) -> str:
    """Return a deterministic SHA256 hex fingerprint of the effective config."""
    canonical = json.dumps(asdict(cfg), sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

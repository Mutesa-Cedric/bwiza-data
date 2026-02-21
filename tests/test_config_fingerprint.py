"""Tests for config fingerprinting."""

from apps.common.config_fingerprint import fingerprint_config
from apps.common.config_types import AppConfig


def test_same_config_same_fingerprint():
    a = fingerprint_config(AppConfig())
    b = fingerprint_config(AppConfig())
    assert a == b


def test_different_config_different_fingerprint():
    cfg_a = AppConfig()
    cfg_b = AppConfig()
    cfg_b.lid.min_confidence = 0.95
    assert fingerprint_config(cfg_a) != fingerprint_config(cfg_b)


def test_fingerprint_is_hex_sha256():
    fp = fingerprint_config(AppConfig())
    assert len(fp) == 64
    assert all(c in "0123456789abcdef" for c in fp)

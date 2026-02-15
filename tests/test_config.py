"""Tests for config loading and validation."""

import tempfile
from pathlib import Path

import pytest
import yaml

from apps.common.config import load_config
from apps.common.config_types import AppConfig


def _write_yaml(data: dict, path: Path) -> Path:
    with open(path, "w") as f:
        yaml.dump(data, f)
    return path


def test_load_default_config():
    cfg = load_config("configs/default.yaml")
    assert isinstance(cfg, AppConfig)
    assert cfg.lid.min_confidence == 0.80
    assert cfg.filters.min_chars == 200
    assert cfg.sharding.target_compressed_mb == 200
    assert cfg.logging.level == "INFO"


def test_load_config_missing_file():
    with pytest.raises(FileNotFoundError):
        load_config("nonexistent.yaml")


def test_invalid_lid_confidence():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "bad.yaml"
        _write_yaml({"lid": {"min_confidence": 1.5}}, p)
        with pytest.raises(ValueError, match="lid.min_confidence"):
            load_config(p)


def test_invalid_min_chars():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "bad.yaml"
        _write_yaml({"filters": {"min_chars": -1}}, p)
        with pytest.raises(ValueError, match="filters.min_chars"):
            load_config(p)


def test_invalid_shard_size():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "bad.yaml"
        _write_yaml({"sharding": {"target_compressed_mb": 0}}, p)
        with pytest.raises(ValueError, match="sharding.target_compressed_mb"):
            load_config(p)


def test_empty_yaml_uses_defaults():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "empty.yaml"
        _write_yaml({}, p)
        cfg = load_config(p)
        assert cfg.lid.min_confidence == 0.80
        assert cfg.filters.min_chars == 200


def test_invalid_section_type():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "bad.yaml"
        _write_yaml({"lid": "not_a_dict"}, p)
        with pytest.raises(ValueError, match="must be a mapping"):
            load_config(p)

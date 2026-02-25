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
    assert cfg.filters.max_chars == 100_000
    assert cfg.filters.min_words == 30
    assert cfg.filters.max_word_ngram_rep_2 == 0.30
    assert cfg.filters.max_non_latin_alpha_ratio == 0.10
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


def test_s3_enabled_requires_bucket():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "bad.yaml"
        _write_yaml({"s3": {"enabled": True, "bucket": ""}}, p)
        with pytest.raises(ValueError, match="s3.bucket must be set"):
            load_config(p)


def test_s3_enabled_with_bucket_ok():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "ok.yaml"
        _write_yaml({"s3": {"enabled": True, "bucket": "my-bucket"}}, p)
        cfg = load_config(p)
        assert cfg.s3.enabled is True
        assert cfg.s3.bucket == "my-bucket"
        assert cfg.s3.verify_after_upload is True


def test_s3_disabled_no_bucket_ok():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "ok.yaml"
        _write_yaml({"s3": {"enabled": False}}, p)
        cfg = load_config(p)
        assert cfg.s3.enabled is False


def test_targeted_defaults_loaded():
    cfg = load_config("configs/default.yaml")
    assert cfg.targeted.enabled is False
    assert cfg.targeted.max_pages == 50000
    assert cfg.targeted.per_domain_max_pages == 5000
    assert cfg.targeted.crawl_delay_s == 0.5
    assert cfg.targeted.output_source == "targeted_web"
    assert cfg.targeted.allowed_content_types == ["text/html", "application/pdf"]
    assert cfg.targeted.pdf_max_pages == 500
    assert cfg.targeted.pdf_min_text_ratio == 0.10


def test_targeted_invalid_max_pages():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "bad.yaml"
        _write_yaml({"targeted": {"max_pages": 0}}, p)
        with pytest.raises(ValueError, match="targeted.max_pages"):
            load_config(p)


def test_targeted_invalid_crawl_delay():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "bad.yaml"
        _write_yaml({"targeted": {"crawl_delay_s": -1}}, p)
        with pytest.raises(ValueError, match="targeted.crawl_delay_s"):
            load_config(p)


def test_targeted_invalid_max_response_bytes():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "bad.yaml"
        _write_yaml({"targeted": {"max_response_bytes": 0}}, p)
        with pytest.raises(ValueError, match="targeted.max_response_bytes"):
            load_config(p)


def test_parallel_defaults_loaded():
    cfg = load_config("configs/default.yaml")
    assert cfg.parallel.enabled is False
    assert cfg.parallel.min_chars == 120
    assert cfg.parallel.min_lid_conf == 0.85
    assert cfg.parallel.extract_mode == "page_pairs"
    assert cfg.parallel.output_source == "parallel_web"


def test_books_defaults_loaded():
    cfg = load_config("configs/default.yaml")
    assert cfg.books.enabled is False
    assert cfg.books.seeds_file == "configs/books_sources.txt"
    assert cfg.books.concurrency == 8
    assert cfg.books.domain_delay_s == 0.25
    assert cfg.books.output_source == "books_corpus"
    assert cfg.books.allowed_content_types == ["text/html", "application/pdf"]


def test_books_invalid_concurrency():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "bad.yaml"
        _write_yaml({"books": {"concurrency": 0}}, p)
        with pytest.raises(ValueError, match="books.concurrency"):
            load_config(p)


def test_books_invalid_lid_confidence():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "bad.yaml"
        _write_yaml({"books": {"min_lid_confidence": 1.1}}, p)
        with pytest.raises(ValueError, match="books.min_lid_confidence"):
            load_config(p)


def test_parallel_invalid_min_chars():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "bad.yaml"
        _write_yaml({"parallel": {"min_chars": 0}}, p)
        with pytest.raises(ValueError, match="parallel.min_chars"):
            load_config(p)


def test_parallel_invalid_min_lid_conf():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "bad.yaml"
        _write_yaml({"parallel": {"min_lid_conf": 1.5}}, p)
        with pytest.raises(ValueError, match="parallel.min_lid_conf"):
            load_config(p)


def test_instructions_defaults_loaded():
    cfg = load_config("configs/default.yaml")
    assert cfg.instructions.enabled is False
    assert cfg.instructions.min_chars_prompt == 4
    assert cfg.instructions.max_chars_response == 8000
    assert cfg.instructions.target_count == 20000
    assert cfg.instructions.output_source == "instructions_rw"


def test_instructions_invalid_target_count():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "bad.yaml"
        _write_yaml({"instructions": {"target_count": 0}}, p)
        with pytest.raises(ValueError, match="instructions.target_count"):
            load_config(p)


def test_invalid_max_chars():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "bad.yaml"
        _write_yaml({"filters": {"max_chars": 0}}, p)
        with pytest.raises(ValueError, match="filters.max_chars"):
            load_config(p)


def test_invalid_min_words():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "bad.yaml"
        _write_yaml({"filters": {"min_words": -1}}, p)
        with pytest.raises(ValueError, match="filters.min_words"):
            load_config(p)


def test_invalid_ngram_rep_threshold():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "bad.yaml"
        _write_yaml({"filters": {"max_word_ngram_rep_2": 1.5}}, p)
        with pytest.raises(ValueError, match="max_word_ngram_rep_2"):
            load_config(p)


def test_invalid_non_latin_ratio():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "bad.yaml"
        _write_yaml({"filters": {"max_non_latin_alpha_ratio": -0.1}}, p)
        with pytest.raises(ValueError, match="max_non_latin_alpha_ratio"):
            load_config(p)

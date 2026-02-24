"""Config loader with validation."""

from pathlib import Path

import yaml

from apps.common.config_types import (
    AppConfig,
    CCConfig,
    CCIndexConfig,
    DedupConfig,
    FiltersConfig,
    GuardrailsConfig,
    InstructionsConfig,
    LidConfig,
    LoggingConfig,
    OutputConfig,
    ParallelConfig,
    S3Config,
    ShardingConfig,
    TargetedConfig,
    WaybackConfig,
    WikiConfig,
)

_SECTION_MAP = {
    "lid": LidConfig,
    "filters": FiltersConfig,
    "sharding": ShardingConfig,
    "s3": S3Config,
    "cc": CCConfig,
    "output": OutputConfig,
    "logging": LoggingConfig,
    "targeted": TargetedConfig,
    "parallel": ParallelConfig,
    "instructions": InstructionsConfig,
    "guardrails": GuardrailsConfig,
    "dedup": DedupConfig,
    "wiki": WikiConfig,
    "cc_index": CCIndexConfig,
    "wayback": WaybackConfig,
}


def load_config(path: str | Path = "configs/default.yaml") -> AppConfig:
    """Load and validate YAML config, returning a typed AppConfig."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path) as f:
        raw = yaml.safe_load(f) or {}

    sections = {}
    for key, cls in _SECTION_MAP.items():
        section_data = raw.get(key, {})
        if not isinstance(section_data, dict):
            raise ValueError(
                f"Config section '{key}' must be a mapping, got {type(section_data).__name__}"
            )
        sections[key] = cls(**section_data)

    cfg = AppConfig(**sections)
    _validate(cfg)
    return cfg


def _validate(cfg: AppConfig) -> None:
    if not 0 <= cfg.lid.min_confidence <= 1:
        raise ValueError(f"lid.min_confidence must be in [0, 1], got {cfg.lid.min_confidence}")

    if cfg.filters.min_chars <= 0:
        raise ValueError(f"filters.min_chars must be > 0, got {cfg.filters.min_chars}")

    if not 0 <= cfg.filters.max_url_ratio <= 1:
        raise ValueError(
            f"filters.max_url_ratio must be in [0, 1], got {cfg.filters.max_url_ratio}"
        )

    if not 0 <= cfg.filters.max_repeat_line_ratio <= 1:
        val = cfg.filters.max_repeat_line_ratio
        raise ValueError(f"filters.max_repeat_line_ratio must be in [0, 1], got {val}")

    if not 0 <= cfg.filters.min_alpha_ratio <= 1:
        raise ValueError(
            f"filters.min_alpha_ratio must be in [0, 1], got {cfg.filters.min_alpha_ratio}"
        )

    if cfg.filters.max_chars <= 0:
        raise ValueError(f"filters.max_chars must be > 0, got {cfg.filters.max_chars}")

    if cfg.filters.min_words <= 0:
        raise ValueError(f"filters.min_words must be > 0, got {cfg.filters.min_words}")

    for _n in (2, 3, 4):
        _attr = f"max_word_ngram_rep_{_n}"
        _val = getattr(cfg.filters, _attr)
        if not 0 <= _val <= 1:
            raise ValueError(f"filters.{_attr} must be in [0, 1], got {_val}")

    if not 0 <= cfg.filters.max_non_latin_alpha_ratio <= 1:
        raise ValueError(
            f"filters.max_non_latin_alpha_ratio must be in [0, 1], "
            f"got {cfg.filters.max_non_latin_alpha_ratio}"
        )

    if cfg.sharding.target_compressed_mb <= 0:
        raise ValueError(
            f"sharding.target_compressed_mb must be > 0, got {cfg.sharding.target_compressed_mb}"
        )

    if cfg.s3.enabled and not cfg.s3.bucket:
        raise ValueError("s3.bucket must be set when s3.enabled is true")

    if cfg.s3.multipart_threshold_mb <= 0:
        raise ValueError(
            f"s3.multipart_threshold_mb must be > 0, got {cfg.s3.multipart_threshold_mb}"
        )

    if cfg.s3.multipart_chunk_mb <= 0:
        raise ValueError(f"s3.multipart_chunk_mb must be > 0, got {cfg.s3.multipart_chunk_mb}")

    if cfg.targeted.max_pages <= 0:
        raise ValueError(f"targeted.max_pages must be > 0, got {cfg.targeted.max_pages}")

    if cfg.targeted.per_domain_max_pages <= 0:
        raise ValueError(
            f"targeted.per_domain_max_pages must be > 0, got {cfg.targeted.per_domain_max_pages}"
        )

    if cfg.targeted.crawl_delay_s < 0:
        raise ValueError(f"targeted.crawl_delay_s must be >= 0, got {cfg.targeted.crawl_delay_s}")

    if cfg.targeted.max_response_bytes <= 0:
        raise ValueError(
            f"targeted.max_response_bytes must be > 0, got {cfg.targeted.max_response_bytes}"
        )

    if cfg.parallel.min_chars <= 0:
        raise ValueError(f"parallel.min_chars must be > 0, got {cfg.parallel.min_chars}")

    if not 0 <= cfg.parallel.min_lid_conf <= 1:
        raise ValueError(
            f"parallel.min_lid_conf must be in [0, 1], got {cfg.parallel.min_lid_conf}"
        )

    if cfg.parallel.max_pages <= 0:
        raise ValueError(f"parallel.max_pages must be > 0, got {cfg.parallel.max_pages}")

    if cfg.instructions.min_chars_prompt <= 0:
        raise ValueError(
            f"instructions.min_chars_prompt must be > 0, got {cfg.instructions.min_chars_prompt}"
        )

    if cfg.instructions.max_chars_response <= 0:
        val = cfg.instructions.max_chars_response
        raise ValueError(f"instructions.max_chars_response must be > 0, got {val}")

    if cfg.instructions.target_count <= 0:
        raise ValueError(
            f"instructions.target_count must be > 0, got {cfg.instructions.target_count}"
        )

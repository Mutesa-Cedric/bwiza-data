"""Typed config dataclasses for bwiza-data."""

from dataclasses import dataclass, field


@dataclass
class LidConfig:
    min_confidence: float = 0.80


@dataclass
class FiltersConfig:
    min_chars: int = 200
    max_url_ratio: float = 0.20
    max_repeat_line_ratio: float = 0.30
    min_alpha_ratio: float = 0.70


@dataclass
class ShardingConfig:
    target_compressed_mb: int = 200
    local_dir: str = "outputs/shards"


@dataclass
class S3Config:
    bucket: str = ""
    prefix: str = "bwiza/cc/v1/"


@dataclass
class LoggingConfig:
    level: str = "INFO"


@dataclass
class AppConfig:
    lid: LidConfig = field(default_factory=LidConfig)
    filters: FiltersConfig = field(default_factory=FiltersConfig)
    sharding: ShardingConfig = field(default_factory=ShardingConfig)
    s3: S3Config = field(default_factory=S3Config)
    logging: LoggingConfig = field(default_factory=LoggingConfig)

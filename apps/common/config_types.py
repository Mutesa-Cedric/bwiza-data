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
    enabled: bool = True
    compression: str = "zstd"
    target_compressed_mb: int = 200
    local_dir: str = "outputs/shards"
    filename_prefix: str = "bwiza"
    flush_every_n: int = 500


@dataclass
class S3Config:
    enabled: bool = False
    bucket: str = ""
    prefix: str = "bwiza/cc/v1/"
    region: str = ""
    profile: str = ""
    endpoint_url: str = ""
    multipart_threshold_mb: int = 64
    multipart_chunk_mb: int = 16
    max_retries: int = 8
    retry_backoff_s: int = 2
    verify_after_upload: bool = True
    keep_local_after_upload: bool = True
    upload_manifests: bool = True
    upload_stats: bool = True


@dataclass
class CCConfig:
    crawl: str = "CC-MAIN-2025-01"
    wet_paths_file: str = "configs/wet_sample_urls.txt"
    max_wet_files: int = 10
    user_agent: str = "bwiza-data/0.1"
    request_timeout_s: int = 60
    max_retries: int = 5
    retry_backoff_s: int = 2


@dataclass
class OutputConfig:
    local_dir: str = "outputs/cc"
    shard_prefix: str = "cc_mvp"
    max_docs_per_run: int = 0


@dataclass
class LoggingConfig:
    level: str = "INFO"


@dataclass
class AppConfig:
    lid: LidConfig = field(default_factory=LidConfig)
    filters: FiltersConfig = field(default_factory=FiltersConfig)
    sharding: ShardingConfig = field(default_factory=ShardingConfig)
    s3: S3Config = field(default_factory=S3Config)
    cc: CCConfig = field(default_factory=CCConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)

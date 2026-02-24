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
    max_chars: int = 100_000
    min_words: int = 30
    max_word_ngram_rep_2: float = 0.30
    max_word_ngram_rep_3: float = 0.25
    max_word_ngram_rep_4: float = 0.20
    max_non_latin_alpha_ratio: float = 0.10


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
    crawl: str = "CC-MAIN-2026-04"
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
class TargetedConfig:
    enabled: bool = False
    seeds_file: str = "configs/targeted_domains.txt"
    max_pages: int = 20000
    per_domain_max_pages: int = 5000
    concurrency: int = 8
    request_timeout_s: int = 30
    max_retries: int = 5
    retry_backoff_s: int = 2
    user_agent: str = "bwiza-data/0.1"
    obey_robots_txt: bool = True
    crawl_delay_s: float = 1.0
    max_response_bytes: int = 8_000_000
    allowed_content_types: list[str] = field(
        default_factory=lambda: ["text/html", "application/pdf"]
    )
    output_source: str = "targeted_web"
    min_lid_confidence: float = 0.85
    pdf_max_pages: int = 500
    pdf_min_text_ratio: float = 0.10


@dataclass
class ParallelConfig:
    enabled: bool = False
    seeds_file: str = "configs/parallel_seeds.txt"
    max_pages: int = 20000
    per_domain_max_pages: int = 5000
    concurrency: int = 8
    request_timeout_s: int = 30
    max_retries: int = 5
    retry_backoff_s: int = 2
    obey_robots_txt: bool = True
    crawl_delay_s: float = 1.0
    max_response_bytes: int = 8_000_000
    extract_mode: str = "page_pairs"
    min_chars: int = 120
    min_lid_conf: float = 0.85
    output_source: str = "parallel_web"


@dataclass
class InstructionsConfig:
    enabled: bool = False
    seed_file: str = "configs/instruction_seeds.jsonl"
    output_source: str = "instructions_rw"
    min_chars_prompt: int = 4
    min_chars_response: int = 8
    max_chars_prompt: int = 4000
    max_chars_response: int = 8000
    allow_english_ratio: float = 0.05
    target_count: int = 20000


@dataclass
class WikiConfig:
    enabled: bool = False
    dump_url: str = (
        "https://dumps.wikimedia.org/rwwiki/latest/rwwiki-latest-pages-articles.xml.bz2"
    )
    output_dir: str = "outputs/wiki"
    output_source: str = "wikipedia"
    max_articles: int = 0


@dataclass
class DatasetImportConfig:
    enabled: bool = False
    output_dir: str = "outputs/dataset_import"


@dataclass
class CCIndexConfig:
    enabled: bool = False
    crawls: list[str] = field(default_factory=list)
    discover_crawls: bool = True
    min_crawl_date: str = "2024-01"
    max_crawl_date: str = ""
    max_crawls: int = 6
    domain_queries: list[str] = field(default_factory=lambda: ["*.rw/*"])
    extra_domain_queries: list[str] = field(default_factory=list)
    cdx_page_size: int = 5
    cdx_timeout_s: int = 30
    cdx_max_retries: int = 3
    cdx_retry_backoff_s: int = 2
    cdx_rate_limit_s: float = 0.5
    warc_concurrency: int = 8
    warc_timeout_s: int = 30
    warc_max_retries: int = 3
    warc_retry_backoff_s: int = 2
    max_records: int = 0
    output_source: str = "cc_index"
    user_agent: str = "bwiza-data/0.1"
    status_filter: list[str] = field(default_factory=lambda: ["200"])
    mime_filter: list[str] = field(default_factory=lambda: ["text/html"])


@dataclass
class WaybackConfig:
    enabled: bool = False
    domains: list[str] = field(
        default_factory=lambda: [
            "igihe.com",
            "umuseke.rw",
            "ktpress.rw",
            "newtimes.co.rw",
            "kigalitoday.com",
            "inyarwanda.com",
        ]
    )
    from_year: int = 2015
    to_year: int = 2025
    cdx_timeout_s: int = 30
    cdx_max_retries: int = 3
    cdx_retry_backoff_s: int = 5
    cdx_rate_limit_s: float = 1.0
    fetch_concurrency: int = 1
    fetch_timeout_s: int = 30
    fetch_rate_limit_s: float = 1.0
    fetch_max_retries: int = 3
    fetch_retry_backoff_s: int = 5
    max_records: int = 0
    output_source: str = "wayback"
    user_agent: str = "bwiza-data/0.1 (kinyarwanda-corpus)"
    status_filter: list[str] = field(default_factory=lambda: ["200"])
    mime_filter: list[str] = field(default_factory=lambda: ["text/html"])


@dataclass
class DedupConfig:
    store_path: str = ""
    fuzzy_threshold: float = 0.8
    fuzzy_num_perm: int = 128
    enable_fuzzy: bool = True


@dataclass
class GuardrailsConfig:
    max_items: int = 0
    max_runtime_s: int = 0
    max_bytes_written: int = 0
    max_failed_items: int = 0


@dataclass
class AppConfig:
    lid: LidConfig = field(default_factory=LidConfig)
    filters: FiltersConfig = field(default_factory=FiltersConfig)
    sharding: ShardingConfig = field(default_factory=ShardingConfig)
    s3: S3Config = field(default_factory=S3Config)
    cc: CCConfig = field(default_factory=CCConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    targeted: TargetedConfig = field(default_factory=TargetedConfig)
    parallel: ParallelConfig = field(default_factory=ParallelConfig)
    instructions: InstructionsConfig = field(default_factory=InstructionsConfig)
    guardrails: GuardrailsConfig = field(default_factory=GuardrailsConfig)
    dedup: DedupConfig = field(default_factory=DedupConfig)
    wiki: WikiConfig = field(default_factory=WikiConfig)
    dataset_import: DatasetImportConfig = field(default_factory=DatasetImportConfig)
    cc_index: CCIndexConfig = field(default_factory=CCIndexConfig)
    wayback: WaybackConfig = field(default_factory=WaybackConfig)

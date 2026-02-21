"""Stable RunReport schema for per-run quality reporting."""

import json
from dataclasses import asdict, dataclass, field


@dataclass
class RunReport:
    """Per-run report with identity, throughput, output, quality, and reproducibility."""

    # Identity
    run_id: str = ""
    source: str = ""
    crawl_id: str = ""

    # Timing
    started_at: str = ""
    ended_at: str = ""

    # Throughput
    wet_files_attempted: int = 0
    wet_files_succeeded: int = 0
    docs_seen: int = 0
    docs_kept: int = 0
    docs_deduped: int = 0

    # Output
    bytes_written: int = 0
    shards_written: int = 0
    token_estimate_total: int = 0
    avg_doc_chars_kept: float = 0.0

    # Quality
    reject_reasons: dict = field(default_factory=dict)
    lid_score_histogram: dict = field(default_factory=dict)
    doc_length_histogram: dict = field(default_factory=dict)
    top_domains_kept: list = field(default_factory=list)

    # Reproducibility
    config_fingerprint: str = ""
    git_commit: str = ""
    notes: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: dict) -> "RunReport":
        known = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)

    @classmethod
    def from_json(cls, text: str) -> "RunReport":
        return cls.from_dict(json.loads(text))

"""RunReport builder: collects metrics during mining and writes report."""

import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from apps.common.config_fingerprint import fingerprint_config
from apps.common.config_types import AppConfig
from apps.common.histogram import LENGTH_BINS, LID_BINS, update_histogram
from apps.common.logging import get_logger
from apps.common.report_schema import RunReport

log = get_logger(__name__)


class ReportBuilder:
    """Accumulates metrics during a mining run and produces a RunReport."""

    def __init__(self, cfg: AppConfig, run_id: str, source: str = "commoncrawl") -> None:
        self._cfg = cfg
        self._run_id = run_id
        self._source = source
        self._started_at = datetime.now(timezone.utc).isoformat()

        self._wet_attempted = 0
        self._wet_succeeded = 0
        self._docs_seen = 0
        self._docs_kept = 0
        self._docs_deduped = 0
        self._total_kept_chars = 0
        self._bytes_written = 0
        self._shards_written = 0
        self._token_estimate = 0

        self._reject_reasons: Counter = Counter()
        self._lid_histogram: dict = {}
        self._length_histogram: dict = {}
        self._domain_counts: Counter = Counter()

    def record_wet_attempt(self) -> None:
        self._wet_attempted += 1

    def record_wet_success(self) -> None:
        self._wet_succeeded += 1

    def record_doc_seen(self) -> None:
        self._docs_seen += 1

    def record_doc_kept(self, text_length: int, lid_score: float, domain: str = "") -> None:
        self._docs_kept += 1
        self._total_kept_chars += text_length
        update_histogram(self._lid_histogram, lid_score, LID_BINS)
        update_histogram(self._length_histogram, text_length, LENGTH_BINS)
        if domain:
            self._domain_counts[domain] += 1

    def record_reject(self, reason: str, lid_score: float = 0.0) -> None:
        self._reject_reasons[reason] += 1
        if lid_score > 0:
            update_histogram(self._lid_histogram, lid_score, LID_BINS)

    def record_dedup(self) -> None:
        self._docs_deduped += 1

    def record_shard_closed(self, shard_bytes: int, token_estimate: int) -> None:
        self._shards_written += 1
        self._bytes_written += shard_bytes
        self._token_estimate += token_estimate

    def build(self) -> RunReport:
        ended_at = datetime.now(timezone.utc).isoformat()
        avg_chars = self._total_kept_chars / self._docs_kept if self._docs_kept else 0.0

        top_domains = [{"domain": d, "docs": c} for d, c in self._domain_counts.most_common(20)]

        return RunReport(
            run_id=self._run_id,
            source=self._source,
            crawl_id=self._cfg.cc.crawl,
            started_at=self._started_at,
            ended_at=ended_at,
            wet_files_attempted=self._wet_attempted,
            wet_files_succeeded=self._wet_succeeded,
            docs_seen=self._docs_seen,
            docs_kept=self._docs_kept,
            docs_deduped=self._docs_deduped,
            bytes_written=self._bytes_written,
            shards_written=self._shards_written,
            token_estimate_total=self._token_estimate,
            avg_doc_chars_kept=round(avg_chars, 1),
            reject_reasons=dict(self._reject_reasons.most_common()),
            lid_score_histogram=dict(sorted(self._lid_histogram.items())),
            doc_length_histogram=dict(sorted(self._length_histogram.items())),
            top_domains_kept=top_domains,
            config_fingerprint=fingerprint_config(self._cfg),
            git_commit=_get_git_commit(),
        )

    def write(self, out_dir: str = "outputs/reports") -> Path:
        report = self.build()
        path = Path(out_dir) / f"{self._run_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(report.to_json())
        log.info("Report written to %s", path)
        return path


def _get_git_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except Exception:
        return ""

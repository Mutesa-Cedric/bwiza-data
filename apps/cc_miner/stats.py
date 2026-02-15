"""Run-level statistics for CC miner."""

import json
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from apps.common.logging import get_logger

log = get_logger(__name__)


@dataclass
class RunStats:
    """Tracks statistics for a mining run."""

    start_time: float = field(default_factory=time.time)
    wet_files_processed: int = 0
    docs_seen: int = 0
    docs_kept: int = 0
    duplicates: int = 0
    total_kept_chars: int = 0
    reject_reasons: Counter = field(default_factory=Counter)

    @property
    def keep_ratio(self) -> float:
        return self.docs_kept / self.docs_seen if self.docs_seen else 0.0

    @property
    def avg_doc_length(self) -> float:
        return self.total_kept_chars / self.docs_kept if self.docs_kept else 0.0

    @property
    def token_estimate(self) -> int:
        return int(self.total_kept_chars / 4)

    def to_dict(self) -> dict:
        return {
            "start_time": self.start_time,
            "end_time": time.time(),
            "elapsed_s": round(time.time() - self.start_time, 2),
            "wet_files_processed": self.wet_files_processed,
            "docs_seen": self.docs_seen,
            "docs_kept": self.docs_kept,
            "duplicates": self.duplicates,
            "keep_ratio": round(self.keep_ratio, 4),
            "avg_doc_length": round(self.avg_doc_length, 1),
            "token_estimate": self.token_estimate,
            "reject_reasons": dict(self.reject_reasons.most_common()),
        }

    def write_json(self, out_dir: str | Path, run_id: str) -> Path:
        path = Path(out_dir) / run_id / "stats.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)
        log.info("Stats written to %s", path)
        return path

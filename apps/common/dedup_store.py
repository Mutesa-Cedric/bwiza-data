"""Persistent cross-run deduplication store backed by SQLite."""

import sqlite3
from pathlib import Path

from apps.common.dedup_minhash import MinHashDedup
from apps.common.logging import get_logger

log = get_logger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS exact_hashes (
    sha256 TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    run_id TEXT NOT NULL,
    added_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS fuzzy_docs (
    doc_id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    run_id TEXT NOT NULL,
    added_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


class DedupStore:
    """Persistent dedup store combining exact (SQLite) and fuzzy (MinHash LSH)."""

    def __init__(
        self,
        db_path: str | Path,
        fuzzy_threshold: float = 0.8,
        fuzzy_num_perm: int = 128,
        enable_fuzzy: bool = True,
    ) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

        self._enable_fuzzy = enable_fuzzy
        self._fuzzy: MinHashDedup | None = None
        if enable_fuzzy:
            self._fuzzy = MinHashDedup(threshold=fuzzy_threshold, num_perm=fuzzy_num_perm)

        self._exact_hits = 0
        self._fuzzy_hits = 0

        log.info("DedupStore opened at %s (fuzzy=%s)", self._db_path, enable_fuzzy)

    # ── exact dedup ──────────────────────────────────────────────

    def has_exact(self, sha256: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM exact_hashes WHERE sha256 = ?", (sha256,)
        ).fetchone()
        return row is not None

    def add_exact(self, sha256: str, source: str, run_id: str) -> None:
        self._conn.execute(
            "INSERT OR IGNORE INTO exact_hashes (sha256, source, run_id) VALUES (?, ?, ?)",
            (sha256, source, run_id),
        )
        self._conn.commit()

    def check_and_add_exact(self, sha256: str, source: str, run_id: str) -> bool:
        """Return True if duplicate (already seen). Otherwise insert and return False."""
        if self.has_exact(sha256):
            self._exact_hits += 1
            return True
        self.add_exact(sha256, source, run_id)
        return False

    # ── fuzzy dedup ──────────────────────────────────────────────

    def check_and_add_fuzzy(self, text: str, doc_id: str, source: str, run_id: str) -> bool:
        """Return True if near-duplicate. Otherwise index and return False."""
        if not self._enable_fuzzy or self._fuzzy is None:
            return False
        if self._fuzzy.check_and_add(text):
            self._fuzzy_hits += 1
            return True
        # Record in SQLite for auditing (not used for lookup — LSH is in-memory)
        self._conn.execute(
            "INSERT OR IGNORE INTO fuzzy_docs (doc_id, source, run_id) VALUES (?, ?, ?)",
            (doc_id, source, run_id),
        )
        self._conn.commit()
        return False

    # ── combined check ───────────────────────────────────────────

    def is_duplicate(
        self, sha256: str, text: str, doc_id: str, source: str, run_id: str
    ) -> tuple[bool, str]:
        """Combined exact + fuzzy check. Returns (is_dup, reason)."""
        if self.check_and_add_exact(sha256, source, run_id):
            return True, "reject.dedup.exact"
        if self.check_and_add_fuzzy(text, doc_id, source, run_id):
            return True, "reject.dedup.fuzzy"
        return False, ""

    # ── stats ────────────────────────────────────────────────────

    def stats(self) -> dict:
        exact_total = self._conn.execute("SELECT COUNT(*) FROM exact_hashes").fetchone()[0]
        fuzzy_total = self._conn.execute("SELECT COUNT(*) FROM fuzzy_docs").fetchone()[0]

        # Per-source counts
        rows = self._conn.execute(
            "SELECT source, COUNT(*) FROM exact_hashes GROUP BY source"
        ).fetchall()
        exact_by_source = {r[0]: r[1] for r in rows}

        return {
            "exact_total": exact_total,
            "fuzzy_total": fuzzy_total,
            "exact_hits_this_session": self._exact_hits,
            "fuzzy_hits_this_session": self._fuzzy_hits,
            "exact_by_source": exact_by_source,
        }

    # ── lifecycle ────────────────────────────────────────────────

    def close(self) -> None:
        log.info("DedupStore closing: %s", self.stats())
        self._conn.close()

    def __enter__(self) -> "DedupStore":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

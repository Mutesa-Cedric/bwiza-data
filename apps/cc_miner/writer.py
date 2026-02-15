"""Local JSONL writer for CC miner MVP output."""

import json
from pathlib import Path

from apps.common.config_types import AppConfig
from apps.common.logging import get_logger

log = get_logger(__name__)


class LocalWriter:
    """Write documents as JSONL to a local file with periodic flushing."""

    def __init__(self, cfg: AppConfig, run_id: str) -> None:
        out_dir = Path(cfg.output.local_dir) / run_id
        out_dir.mkdir(parents=True, exist_ok=True)
        self._path = out_dir / "part-000001.jsonl"
        self._tmp_path = self._path.with_suffix(".jsonl.tmp")
        self._file = open(self._tmp_path, "w", encoding="utf-8")
        self._count = 0
        log.info("Writer opened: %s", self._tmp_path)

    @property
    def path(self) -> Path:
        return self._path

    @property
    def count(self) -> int:
        return self._count

    def write(self, doc_dict: dict) -> None:
        line = json.dumps(doc_dict, ensure_ascii=False)
        self._file.write(line + "\n")
        self._count += 1
        if self._count % 500 == 0:
            self._file.flush()

    def close(self) -> None:
        self._file.flush()
        self._file.close()
        if self._count > 0:
            self._tmp_path.rename(self._path)
            log.info("Writer finalized: %s (%d docs)", self._path, self._count)
        else:
            self._tmp_path.unlink(missing_ok=True)
            log.info("Writer closed with 0 docs, removed temp file")

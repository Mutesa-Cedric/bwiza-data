"""Zstd-compressed JSONL shard writer with rotation."""

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import orjson
import zstandard as zstd

from apps.common.checksum import sha256_file
from apps.common.logging import get_logger
from apps.common.shard_naming import shard_name
from apps.common.token_estimate import estimate_tokens_from_doc

log = get_logger(__name__)


@dataclass
class ShardMeta:
    """Metadata for a closed shard."""

    filename: str
    path: str
    bytes: int
    records_count: int
    token_estimate: int
    checksum: str
    created_at: str


class ShardWriter:
    """Write documents as zstd-compressed JSONL with automatic rotation."""

    def __init__(self, cfg_sharding, source: str, run_id: str) -> None:
        self._cfg = cfg_sharding
        self._source = source
        self._run_id = run_id
        self._part = 0
        self._target_bytes = cfg_sharding.target_compressed_mb * 1024 * 1024
        self._flush_every_n = cfg_sharding.flush_every_n
        self._out_dir = Path(cfg_sharding.local_dir) / run_id
        self._out_dir.mkdir(parents=True, exist_ok=True)
        self._closed_shards: list[ShardMeta] = []
        self._records_in_current = 0
        self._tokens_in_current = 0
        self._shard_open = False
        self._open_shard()

    @property
    def closed_shards(self) -> list[ShardMeta]:
        return list(self._closed_shards)

    def _open_shard(self) -> None:
        self._part += 1
        self._current_name = shard_name(
            self._cfg.filename_prefix, self._source, self._run_id, self._part
        )
        self._current_path = self._out_dir / self._current_name
        self._tmp_path = self._current_path.with_suffix(".zst.tmp")
        self._raw_file = open(self._tmp_path, "wb")
        self._compressor = zstd.ZstdCompressor()
        self._writer = self._compressor.stream_writer(self._raw_file)
        self._records_in_current = 0
        self._tokens_in_current = 0
        self._shard_open = True

    def write(self, doc_dict: dict) -> ShardMeta | None:
        """Write a document. Returns ShardMeta if rotation happened."""
        if not self._shard_open:
            self._open_shard()
        line = orjson.dumps(doc_dict) + b"\n"
        self._writer.write(line)
        self._records_in_current += 1
        self._tokens_in_current += estimate_tokens_from_doc(doc_dict)

        if self._records_in_current % self._flush_every_n == 0:
            self._writer.flush()

        return self._rotate_if_needed()

    def _rotate_if_needed(self) -> ShardMeta | None:
        self._writer.flush()
        current_size = self._tmp_path.stat().st_size
        if current_size >= self._target_bytes:
            return self._close_current_shard()
        return None

    def _close_current_shard(self) -> ShardMeta:
        self._writer.close()
        self._raw_file.close()

        # Rename tmp -> final
        self._tmp_path.rename(self._current_path)

        checksum = sha256_file(str(self._current_path))
        file_size = self._current_path.stat().st_size

        meta = ShardMeta(
            filename=self._current_name,
            path=str(self._current_path),
            bytes=file_size,
            records_count=self._records_in_current,
            token_estimate=self._tokens_in_current,
            checksum=checksum,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self._closed_shards.append(meta)
        self._shard_open = False
        log.info(
            "Shard closed: %s (%d records, %d bytes)",
            self._current_name,
            meta.records_count,
            meta.bytes,
        )
        return meta

    def close(self) -> ShardMeta | None:
        """Close the current shard. Returns ShardMeta if any records were written."""
        if not self._shard_open:
            return None
        if self._records_in_current > 0:
            return self._close_current_shard()
        else:
            self._writer.close()
            self._raw_file.close()
            self._tmp_path.unlink(missing_ok=True)
            self._shard_open = False
            return None

"""Streaming gzip decompression for WET files."""

import gzip
import io
from collections.abc import Iterator


class _ChunkReader(io.RawIOBase):
    """Wrap a byte chunk iterator as a readable stream."""

    def __init__(self, chunk_iter: Iterator[bytes]) -> None:
        self._iter = chunk_iter
        self._buf = b""

    def readable(self) -> bool:
        return True

    def readinto(self, b: bytearray | memoryview) -> int:  # type: ignore[override]
        try:
            while len(self._buf) < len(b):
                self._buf += next(self._iter)
        except StopIteration:
            pass

        n = min(len(b), len(self._buf))
        if n == 0:
            return 0
        b[:n] = self._buf[:n]
        self._buf = self._buf[n:]
        return n


def iter_text_lines(byte_iter: Iterator[bytes]) -> Iterator[str]:
    """Decompress gzipped byte chunks and yield text lines."""
    raw = _ChunkReader(byte_iter)
    buffered = io.BufferedReader(raw, buffer_size=1 << 16)
    with gzip.open(buffered, mode="rt", encoding="utf-8", errors="replace") as f:
        yield from f

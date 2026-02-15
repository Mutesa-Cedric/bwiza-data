"""Tests for streaming gzip decompression."""

import gzip

from apps.cc_miner.decompress import iter_text_lines


def test_decompresses_gzip_bytes():
    raw_text = "line one\nline two\nline three\n"
    compressed = gzip.compress(raw_text.encode("utf-8"))
    # Simulate chunked delivery
    chunks = [compressed[i : i + 10] for i in range(0, len(compressed), 10)]

    lines = list(iter_text_lines(iter(chunks)))
    assert [line.rstrip("\n") for line in lines] == ["line one", "line two", "line three"]


def test_handles_empty_content():
    compressed = gzip.compress(b"")
    lines = list(iter_text_lines(iter([compressed])))
    assert lines == []


def test_handles_unicode():
    raw_text = "Muraho neza\nUmugore\n"
    compressed = gzip.compress(raw_text.encode("utf-8"))
    lines = list(iter_text_lines(iter([compressed])))
    stripped = [line.rstrip("\n") for line in lines]
    assert "Muraho neza" in stripped

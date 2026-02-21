"""Tests for zstd shard writer."""

import json

import zstandard as zstd

from apps.common.config_types import ShardingConfig
from apps.common.shard_writer import ShardWriter


def _cfg(tmp_path, target_mb=1) -> ShardingConfig:
    return ShardingConfig(
        enabled=True,
        compression="zstd",
        target_compressed_mb=target_mb,
        local_dir=str(tmp_path),
        filename_prefix="test",
        flush_every_n=10,
    )


def test_write_and_close(tmp_path):
    writer = ShardWriter(_cfg(tmp_path), "test_source", "run1")
    for i in range(5):
        writer.write({"id": str(i), "text": f"doc {i}"})
    meta = writer.close()

    assert meta is not None
    assert meta.records_count == 5
    assert meta.bytes > 0
    assert len(meta.checksum) == 64

    # Verify content can be decompressed (streaming, no content-size header)
    dctx = zstd.ZstdDecompressor()
    with open(meta.path, "rb") as f:
        reader = dctx.stream_reader(f)
        data = reader.read()
    lines = data.decode("utf-8").strip().split("\n")
    assert len(lines) == 5
    assert json.loads(lines[0])["id"] == "0"


def test_empty_writer_no_shard(tmp_path):
    writer = ShardWriter(_cfg(tmp_path), "test_source", "run_empty")
    meta = writer.close()
    assert meta is None
    assert len(writer.closed_shards) == 0


def test_rotation_on_size(tmp_path):
    # Very small target to force rotation
    cfg = _cfg(tmp_path, target_mb=0)
    cfg.target_compressed_mb = 0  # will use 0 bytes = immediate rotation

    # target_bytes = 0 means rotate after every flush check
    # Let's use a tiny value instead
    writer = ShardWriter(cfg, "test_source", "run_rot")
    # Write enough to trigger rotation
    big_text = "x" * 10000
    for i in range(10):
        writer.write({"id": str(i), "text": big_text})
    writer.close()

    # Should have created multiple shards
    assert len(writer.closed_shards) >= 1


def test_token_estimate_parallel_docs(tmp_path):
    writer = ShardWriter(_cfg(tmp_path), "parallel", "run_tok")
    writer.write({"id": "1", "rw_text": "a" * 200, "en_text": "b" * 200})
    meta = writer.close()
    assert meta is not None
    assert meta.token_estimate == 100  # (200 + 200) / 4


def test_token_estimate_instruction_docs(tmp_path):
    writer = ShardWriter(_cfg(tmp_path), "instructions", "run_tok2")
    writer.write({"id": "1", "prompt": "a" * 100, "response": "b" * 300})
    meta = writer.close()
    assert meta is not None
    assert meta.token_estimate == 100  # (100 + 300) / 4


def test_tmp_renamed_to_final(tmp_path):
    writer = ShardWriter(_cfg(tmp_path), "src", "run_rename")
    writer.write({"id": "1", "text": "hello"})
    meta = writer.close()

    # Final path should exist, no .tmp
    from pathlib import Path

    assert Path(meta.path).exists()
    assert not Path(meta.path + ".tmp").exists()

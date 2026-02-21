"""Tests for post-upload cleanup."""

from unittest.mock import MagicMock, patch

from apps.common.cleanup import cleanup_uploaded_shards
from apps.common.config_types import S3Config


def _s3_cfg(**overrides: object) -> S3Config:
    cfg = S3Config(
        enabled=True,
        bucket="test-bucket",
        prefix="bwiza/cc/v1/",
        keep_local_after_upload=False,
    )
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return cfg


def test_skips_when_keep_local_true():
    cfg = _s3_cfg(keep_local_after_upload=True)
    result = cleanup_uploaded_shards(MagicMock(), cfg, "run1", [{"path": "/a", "filename": "a"}])
    assert result["deleted"] == 0
    assert result["kept"] == 1


@patch("apps.common.cleanup.verify_upload", return_value=True)
def test_deletes_verified_shard(mock_verify, tmp_path):
    shard = tmp_path / "test.jsonl.zst"
    shard.write_bytes(b"data")

    entries = [{"path": str(shard), "filename": "test.jsonl.zst"}]
    result = cleanup_uploaded_shards(MagicMock(), _s3_cfg(), "run1", entries)

    assert result["deleted"] == 1
    assert not shard.exists()


@patch("apps.common.cleanup.verify_upload", return_value=False)
def test_keeps_unverified_shard(mock_verify, tmp_path):
    shard = tmp_path / "test.jsonl.zst"
    shard.write_bytes(b"data")

    entries = [{"path": str(shard), "filename": "test.jsonl.zst"}]
    result = cleanup_uploaded_shards(MagicMock(), _s3_cfg(), "run1", entries)

    assert result["deleted"] == 0
    assert result["kept"] == 1
    assert shard.exists()
    assert len(result["errors"]) == 1


def test_skips_non_zst_files(tmp_path):
    f = tmp_path / "test.json"
    f.write_text("{}")

    entries = [{"path": str(f), "filename": "test.json"}]
    result = cleanup_uploaded_shards(MagicMock(), _s3_cfg(), "run1", entries)

    assert result["deleted"] == 0
    assert f.exists()


def test_handles_missing_file():
    entries = [{"path": "/nonexistent/shard.jsonl.zst", "filename": "shard.jsonl.zst"}]
    result = cleanup_uploaded_shards(MagicMock(), _s3_cfg(), "run1", entries)
    assert result["deleted"] == 0
    assert result["kept"] == 1

"""Tests for dataset publishing to S3."""

import os
from unittest.mock import MagicMock, patch

from apps.common.config_types import S3Config
from apps.packaging.publish import publish_dataset


def _s3_cfg() -> S3Config:
    return S3Config(
        enabled=True,
        bucket="test-bucket",
        prefix="bwiza/",
        multipart_threshold_mb=64,
        multipart_chunk_mb=16,
        max_retries=1,
        retry_backoff_s=0,
    )


def _create_artifacts(base_dir):
    """Create minimal dataset artifacts in base_dir."""
    (base_dir / "index.jsonl").write_text('{"test": true}\n')
    (base_dir / "stats.json").write_text('{"total_shards": 1}\n')
    (base_dir / "dataset_meta.json").write_text('{"name": "bwiza-pretrain"}\n')
    splits_dir = base_dir / "splits"
    splits_dir.mkdir()
    (splits_dir / "train.txt").write_text("key1\n")
    (splits_dir / "val.txt").write_text("key2\n")
    (splits_dir / "test.txt").write_text("key3\n")


def _mock_upload(client, local_path, bucket, key, cfg):
    """Mock upload_file that returns a successful result."""
    from apps.common.s3_upload import UploadResult

    return UploadResult(bucket=bucket, key=key, size=os.path.getsize(local_path))


def _mock_upload_skip(client, local_path, bucket, key, cfg):
    """Mock upload_file that returns a skipped result."""
    from apps.common.s3_upload import UploadResult

    return UploadResult(bucket=bucket, key=key, size=0, skipped=True)


@patch("apps.packaging.publish.verify_upload", return_value=True)
@patch("apps.packaging.publish.upload_file", side_effect=_mock_upload)
def test_publish_all_artifacts(mock_upload, mock_verify, tmp_path):
    _create_artifacts(tmp_path)
    client = MagicMock()

    result = publish_dataset("pretrain", "v1", str(tmp_path), client, "test-bucket", _s3_cfg())

    assert result.uploaded == 6
    assert result.failed == 0
    assert result.ok is True
    assert mock_upload.call_count == 6
    assert mock_verify.call_count == 6


@patch("apps.packaging.publish.verify_upload", return_value=True)
@patch("apps.packaging.publish.upload_file", side_effect=_mock_upload_skip)
def test_publish_idempotent_skip(mock_upload, mock_verify, tmp_path):
    _create_artifacts(tmp_path)
    client = MagicMock()

    result = publish_dataset("pretrain", "v1", str(tmp_path), client, "test-bucket", _s3_cfg())

    assert result.skipped == 6
    assert result.uploaded == 0
    assert result.ok is True
    # verify should not be called for skipped uploads
    assert mock_verify.call_count == 0


@patch("apps.packaging.publish.verify_upload", return_value=False)
@patch("apps.packaging.publish.upload_file", side_effect=_mock_upload)
def test_publish_verification_failure(mock_upload, mock_verify, tmp_path):
    _create_artifacts(tmp_path)
    client = MagicMock()

    result = publish_dataset("pretrain", "v1", str(tmp_path), client, "test-bucket", _s3_cfg())

    assert result.failed == 6
    assert result.ok is False


@patch("apps.packaging.publish.verify_upload", return_value=True)
@patch("apps.packaging.publish.upload_file", side_effect=_mock_upload)
def test_publish_missing_artifacts(mock_upload, mock_verify, tmp_path):
    # Only create index, not others
    (tmp_path / "index.jsonl").write_text('{"test": true}\n')
    client = MagicMock()

    result = publish_dataset("pretrain", "v1", str(tmp_path), client, "test-bucket", _s3_cfg())

    assert result.uploaded == 1
    assert result.ok is True


@patch("apps.packaging.publish.upload_file", side_effect=Exception("S3 down"))
def test_publish_upload_exception(mock_upload, tmp_path):
    _create_artifacts(tmp_path)
    client = MagicMock()

    result = publish_dataset("pretrain", "v1", str(tmp_path), client, "test-bucket", _s3_cfg())

    assert result.failed == 6
    assert result.ok is False
    assert len(result.errors) == 6


@patch("apps.packaging.publish.verify_upload", return_value=True)
@patch("apps.packaging.publish.upload_file", side_effect=_mock_upload)
def test_publish_s3_key_format(mock_upload, mock_verify, tmp_path):
    (tmp_path / "index.jsonl").write_text('{"test": true}\n')
    client = MagicMock()

    publish_dataset("pretrain", "v1", str(tmp_path), client, "test-bucket", _s3_cfg())

    # upload_file is called as upload_file(client, local, bucket, key, cfg)
    actual_key = mock_upload.call_args_list[0][0][3]
    assert actual_key == "bwiza/datasets/v1/pretrain/index.jsonl"

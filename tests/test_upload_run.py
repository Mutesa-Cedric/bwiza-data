"""Tests for upload_run orchestrator (all mocked)."""

import json
from unittest.mock import MagicMock, patch

from apps.cc_miner.upload_run import upload_run
from apps.common.config_types import AppConfig, OutputConfig, S3Config


def _setup_run(tmp_path, run_id="test_run"):
    """Create fake shard, manifest, and stats for testing."""
    # Create a shard file
    shard_dir = tmp_path / "shards" / run_id
    shard_dir.mkdir(parents=True)
    shard_file = shard_dir / "test_part-000001.jsonl.zst"
    shard_file.write_bytes(b"fake shard data")

    # Create manifest
    manifest_dir = tmp_path / "manifests" / "shards"
    manifest_dir.mkdir(parents=True)
    manifest_file = manifest_dir / f"{run_id}.jsonl"
    entry = {
        "run_id": run_id,
        "source": "commoncrawl",
        "filename": "test_part-000001.jsonl.zst",
        "path": str(shard_file),
        "bytes": 15,
        "records_count": 1,
        "token_estimate": 10,
        "checksum": "abc123",
        "created_at": "2025-01-01T00:00:00",
    }
    manifest_file.write_text(json.dumps(entry) + "\n")

    # Create stats
    stats_dir = tmp_path / "output" / run_id
    stats_dir.mkdir(parents=True)
    stats_file = stats_dir / "stats.json"
    stats_file.write_text(json.dumps({"docs_kept": 10}))

    return shard_file, manifest_file, stats_file


def _cfg(tmp_path) -> AppConfig:
    return AppConfig(
        s3=S3Config(
            enabled=True,
            bucket="test-bucket",
            prefix="bwiza/cc/v1/",
            max_retries=1,
            retry_backoff_s=0,
        ),
        output=OutputConfig(local_dir=str(tmp_path / "output")),
    )


@patch("apps.cc_miner.upload_run.get_s3_client")
@patch("apps.cc_miner.upload_run.upload_file")
@patch("apps.cc_miner.upload_run.verify_upload", return_value=True)
@patch("apps.cc_miner.upload_run.read_manifest")
def test_upload_run_success(mock_manifest, mock_verify, mock_upload, mock_client, tmp_path):
    shard_file, manifest_file, stats_file = _setup_run(tmp_path)

    mock_client.return_value = MagicMock()
    mock_manifest.return_value = [
        {
            "filename": "test_part-000001.jsonl.zst",
            "path": str(shard_file),
        }
    ]

    from apps.common.s3_upload import UploadResult

    mock_upload.return_value = UploadResult(bucket="test-bucket", key="k", size=15, skipped=False)

    cfg = _cfg(tmp_path)
    summary = upload_run(cfg, "test_run")

    assert summary["errors"] == []
    assert summary["uploaded"] >= 1


@patch("apps.cc_miner.upload_run.get_s3_client")
@patch("apps.cc_miner.upload_run.read_manifest")
def test_upload_run_missing_shard(mock_manifest, mock_client, tmp_path):
    mock_client.return_value = MagicMock()
    mock_manifest.return_value = [
        {
            "filename": "missing.jsonl.zst",
            "path": "/nonexistent/missing.jsonl.zst",
        }
    ]

    cfg = _cfg(tmp_path)
    summary = upload_run(cfg, "test_run")

    assert len(summary["errors"]) == 1
    assert "missing" in summary["errors"][0].lower()


@patch("apps.cc_miner.upload_run.get_s3_client")
@patch("apps.cc_miner.upload_run.upload_file")
@patch("apps.cc_miner.upload_run.verify_upload", return_value=True)
@patch("apps.cc_miner.upload_run.read_manifest")
def test_upload_run_skips_existing(mock_manifest, mock_verify, mock_upload, mock_client, tmp_path):
    shard_file, _, _ = _setup_run(tmp_path)
    mock_client.return_value = MagicMock()
    mock_manifest.return_value = [
        {"filename": "test_part-000001.jsonl.zst", "path": str(shard_file)}
    ]

    from apps.common.s3_upload import UploadResult

    mock_upload.return_value = UploadResult(bucket="test-bucket", key="k", size=15, skipped=True)

    cfg = AppConfig(
        s3=S3Config(
            enabled=True,
            bucket="test-bucket",
            prefix="bwiza/cc/v1/",
            max_retries=1,
            retry_backoff_s=0,
            upload_manifests=False,
            upload_stats=False,
        ),
        output=OutputConfig(local_dir=str(tmp_path / "output")),
    )
    summary = upload_run(cfg, "test_run")
    assert summary["skipped"] == 1
    assert summary["uploaded"] == 0
    # Verify not called for skipped uploads
    mock_verify.assert_not_called()


@patch("apps.cc_miner.upload_run.get_s3_client")
@patch("apps.cc_miner.upload_run.read_manifest")
def test_upload_run_empty_manifest(mock_manifest, mock_client, tmp_path):
    mock_client.return_value = MagicMock()
    mock_manifest.return_value = []

    summary = upload_run(_cfg(tmp_path), "test_run")
    assert summary["uploaded"] == 0
    assert summary["errors"] == []

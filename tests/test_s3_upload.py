"""Tests for S3 upload logic (all mocked, no network)."""

from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError

from apps.common.config_types import S3Config
from apps.common.s3_upload import UploadResult, object_exists, upload_file, verify_upload


def _not_found_error():
    return ClientError(
        {"Error": {"Code": "404", "Message": "Not Found"}},
        "HeadObject",
    )


def _s3_cfg(**overrides) -> S3Config:
    defaults = dict(enabled=True, bucket="test-bucket", max_retries=2, retry_backoff_s=0)
    defaults.update(overrides)
    return S3Config(**defaults)


# --- object_exists ---


def test_object_exists_found():
    client = MagicMock()
    client.head_object.return_value = {"ContentLength": 1024}
    exists, size = object_exists(client, "bucket", "key")
    assert exists is True
    assert size == 1024


def test_object_exists_not_found():
    client = MagicMock()
    client.head_object.side_effect = _not_found_error()
    exists, size = object_exists(client, "bucket", "key")
    assert exists is False
    assert size is None


def test_object_exists_other_error():
    client = MagicMock()
    client.head_object.side_effect = ClientError(
        {"Error": {"Code": "403", "Message": "Forbidden"}},
        "HeadObject",
    )
    with pytest.raises(ClientError):
        object_exists(client, "bucket", "key")


# --- upload_file ---


def test_upload_skips_existing(tmp_path):
    f = tmp_path / "test.zst"
    f.write_bytes(b"x" * 100)

    client = MagicMock()
    client.head_object.return_value = {"ContentLength": 100}

    result = upload_file(client, str(f), "bucket", "key", _s3_cfg())
    assert result.skipped is True
    assert result.size == 100
    client.upload_file.assert_not_called()


def test_upload_rejects_size_mismatch(tmp_path):
    f = tmp_path / "test.zst"
    f.write_bytes(b"x" * 100)

    client = MagicMock()
    client.head_object.return_value = {"ContentLength": 50}

    with pytest.raises(ValueError, match="Refusing to overwrite"):
        upload_file(client, str(f), "bucket", "key", _s3_cfg())


def test_upload_succeeds(tmp_path):
    f = tmp_path / "test.zst"
    f.write_bytes(b"x" * 100)

    client = MagicMock()
    client.head_object.side_effect = _not_found_error()

    result = upload_file(client, str(f), "bucket", "key", _s3_cfg())
    assert isinstance(result, UploadResult)
    assert result.skipped is False
    assert result.size == 100
    client.upload_file.assert_called_once()


def test_upload_retries_on_failure(tmp_path):
    f = tmp_path / "test.zst"
    f.write_bytes(b"x" * 100)

    client = MagicMock()
    client.head_object.side_effect = _not_found_error()
    # Fail first attempt, succeed on second
    client.upload_file.side_effect = [
        ClientError({"Error": {"Code": "500", "Message": "Internal"}}, "PutObject"),
        None,
    ]

    result = upload_file(client, str(f), "bucket", "key", _s3_cfg())
    assert result.skipped is False
    assert client.upload_file.call_count == 2


def test_upload_exhausts_retries(tmp_path):
    f = tmp_path / "test.zst"
    f.write_bytes(b"x" * 100)

    client = MagicMock()
    client.head_object.side_effect = _not_found_error()
    client.upload_file.side_effect = ClientError(
        {"Error": {"Code": "500", "Message": "Internal"}}, "PutObject"
    )

    with pytest.raises(RuntimeError, match="Upload failed after 2 attempts"):
        upload_file(client, str(f), "bucket", "key", _s3_cfg())


# --- verify_upload ---


def test_verify_passes(tmp_path):
    f = tmp_path / "test.zst"
    f.write_bytes(b"x" * 100)

    from apps.common.checksum import sha256_file

    checksum = sha256_file(str(f))

    client = MagicMock()
    client.head_object.return_value = {
        "ContentLength": 100,
        "Metadata": {"sha256": checksum},
    }

    assert verify_upload(client, str(f), "bucket", "key") is True


def test_verify_fails_size_mismatch(tmp_path):
    f = tmp_path / "test.zst"
    f.write_bytes(b"x" * 100)

    client = MagicMock()
    client.head_object.return_value = {"ContentLength": 50, "Metadata": {}}

    assert verify_upload(client, str(f), "bucket", "key") is False


def test_verify_fails_checksum_mismatch(tmp_path):
    f = tmp_path / "test.zst"
    f.write_bytes(b"x" * 100)

    client = MagicMock()
    client.head_object.return_value = {
        "ContentLength": 100,
        "Metadata": {"sha256": "wrong"},
    }

    assert verify_upload(client, str(f), "bucket", "key") is False


def test_verify_fails_not_found(tmp_path):
    f = tmp_path / "test.zst"
    f.write_bytes(b"x" * 100)

    client = MagicMock()
    client.head_object.side_effect = _not_found_error()

    assert verify_upload(client, str(f), "bucket", "key") is False


def test_verify_passes_without_remote_checksum(tmp_path):
    """Verification passes if remote has no sha256 metadata (size match only)."""
    f = tmp_path / "test.zst"
    f.write_bytes(b"x" * 100)

    client = MagicMock()
    client.head_object.return_value = {"ContentLength": 100, "Metadata": {}}

    assert verify_upload(client, str(f), "bucket", "key") is True

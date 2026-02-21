"""Tests for index verification against S3."""

from unittest.mock import MagicMock

from apps.common.dataset_index import DatasetIndexEntry, write_index
from apps.packaging.verify_index import verify_entry, verify_index


def _entry(s3_key="prefix/shard_001.jsonl.zst", bytes_=1000):
    return DatasetIndexEntry(
        dataset="pretrain",
        version="v1",
        run_id="run1",
        source="commoncrawl",
        shard_name="shard_001.jsonl.zst",
        s3_bucket="test-bucket",
        s3_key=s3_key,
        bytes=bytes_,
        records=10,
        token_estimate=250,
        checksum_sha256="abc" + "0" * 61,
        created_at="2026-02-21T00:00:00+00:00",
    )


def _mock_client(head_responses=None, missing_keys=None):
    client = MagicMock()
    missing_keys = missing_keys or set()

    class NoSuchKey(Exception):
        pass

    client.exceptions.NoSuchKey = NoSuchKey

    def head_object(Bucket, Key):
        if Key in missing_keys:
            raise NoSuchKey(f"Not found: {Key}")
        if head_responses and Key in head_responses:
            return head_responses[Key]
        return {"ContentLength": 1000}

    client.head_object = MagicMock(side_effect=head_object)
    return client


def test_verify_entry_ok():
    entry = _entry()
    client = _mock_client()
    ok, reason = verify_entry(entry, client, "test-bucket")
    assert ok is True
    assert reason == ""


def test_verify_entry_size_mismatch():
    entry = _entry(bytes_=1000)
    client = _mock_client(head_responses={"prefix/shard_001.jsonl.zst": {"ContentLength": 999}})
    ok, reason = verify_entry(entry, client, "test-bucket")
    assert ok is False
    assert "size_mismatch" in reason


def test_verify_entry_missing():
    entry = _entry()
    client = _mock_client(missing_keys={"prefix/shard_001.jsonl.zst"})
    ok, reason = verify_entry(entry, client, "test-bucket")
    assert ok is False
    assert "missing" in reason


def test_verify_index_all_ok(tmp_path):
    entries = [_entry(s3_key="k1"), _entry(s3_key="k2")]
    index_path = tmp_path / "index.jsonl"
    write_index(entries, index_path)

    client = _mock_client()
    result = verify_index(str(index_path), client, "test-bucket")
    assert result.total == 2
    assert result.ok == 2
    assert result.passed is True


def test_verify_index_with_missing(tmp_path):
    entries = [_entry(s3_key="k1"), _entry(s3_key="k2")]
    index_path = tmp_path / "index.jsonl"
    write_index(entries, index_path)

    client = _mock_client(missing_keys={"k2"})
    result = verify_index(str(index_path), client, "test-bucket")
    assert result.total == 2
    assert result.ok == 1
    assert result.missing == 1
    assert result.passed is False


def test_verify_index_with_size_mismatch(tmp_path):
    entries = [_entry(s3_key="k1", bytes_=500)]
    index_path = tmp_path / "index.jsonl"
    write_index(entries, index_path)

    client = _mock_client()  # returns ContentLength=1000, entry expects 500
    result = verify_index(str(index_path), client, "test-bucket")
    assert result.size_mismatch == 1
    assert result.passed is False


def test_verify_index_empty(tmp_path):
    index_path = tmp_path / "index.jsonl"
    index_path.write_text("")

    client = _mock_client()
    result = verify_index(str(index_path), client, "test-bucket")
    assert result.total == 0
    assert result.passed is True

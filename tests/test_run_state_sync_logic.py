"""Tests for S3 state mirroring (mocked)."""

import json
from unittest.mock import MagicMock

from apps.common.run_state import RunState
from apps.common.run_state_sync import (
    done_s3_key,
    download_state,
    state_s3_key,
    upload_done_list,
    upload_state,
)


def _mock_client():
    return MagicMock()


def _sample_state():
    return RunState(
        run_id="20260221T120000Z",
        pipeline="cc_miner",
        source="commoncrawl",
        status="running",
        items_done=5,
    )


def test_state_s3_key():
    key = state_s3_key("20260221T120000Z")
    assert "run_id=20260221T120000Z" in key
    assert key.endswith("state.json")


def test_done_s3_key():
    key = done_s3_key("20260221T120000Z")
    assert "run_id=20260221T120000Z" in key
    assert key.endswith("done.txt")


def test_upload_state():
    client = _mock_client()
    state = _sample_state()
    upload_state(client, "my-bucket", state)

    client.put_object.assert_called_once()
    call_kwargs = client.put_object.call_args[1]
    assert call_kwargs["Bucket"] == "my-bucket"
    body = json.loads(call_kwargs["Body"].decode("utf-8"))
    assert body["run_id"] == "20260221T120000Z"
    assert body["status"] == "running"


def test_upload_done_list(tmp_path):
    client = _mock_client()
    done_file = tmp_path / "done.txt"
    done_file.write_text("item1\nitem2\n")

    upload_done_list(client, "my-bucket", "run1", str(done_file))
    client.upload_file.assert_called_once()


def test_upload_done_list_missing_file(tmp_path):
    client = _mock_client()
    upload_done_list(client, "my-bucket", "run1", str(tmp_path / "nope.txt"))
    client.upload_file.assert_not_called()


def test_download_state():
    client = _mock_client()
    state = _sample_state()
    body_bytes = state.to_json().encode("utf-8")
    client.get_object.return_value = {"Body": MagicMock(read=MagicMock(return_value=body_bytes))}

    result = download_state(client, "my-bucket", "20260221T120000Z")
    assert result is not None
    assert result.run_id == "20260221T120000Z"
    assert result.status == "running"


def test_download_state_not_found():
    client = _mock_client()
    client.exceptions.NoSuchKey = type("NoSuchKey", (Exception,), {})
    client.get_object.side_effect = client.exceptions.NoSuchKey()

    result = download_state(client, "my-bucket", "nonexistent")
    assert result is None

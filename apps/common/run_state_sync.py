"""Optional S3 mirroring for RunState (crash recovery)."""

from pathlib import Path

from apps.common.logging import get_logger
from apps.common.run_state import RunState

log = get_logger(__name__)

S3_STATE_PREFIX = "bwiza/state/v1/"


def state_s3_key(run_id: str) -> str:
    return f"{S3_STATE_PREFIX}run_id={run_id}/state.json"


def done_s3_key(run_id: str) -> str:
    return f"{S3_STATE_PREFIX}run_id={run_id}/done.txt"


def upload_state(client, bucket: str, state: RunState) -> None:
    """Upload RunState JSON to S3."""
    key = state_s3_key(state.run_id)
    body = state.to_json().encode("utf-8")
    client.put_object(Bucket=bucket, Key=key, Body=body)
    log.debug("State uploaded to s3://%s/%s", bucket, key)


def upload_done_list(client, bucket: str, run_id: str, done_path: str) -> None:
    """Upload the done list file to S3."""
    path = Path(done_path)
    if not path.exists():
        return
    key = done_s3_key(run_id)
    client.upload_file(str(path), bucket, key)
    log.debug("Done list uploaded to s3://%s/%s", bucket, key)


def download_state(client, bucket: str, run_id: str) -> RunState | None:
    """Download RunState from S3. Returns None if not found."""
    key = state_s3_key(run_id)
    try:
        resp = client.get_object(Bucket=bucket, Key=key)
        body = resp["Body"].read().decode("utf-8")
        return RunState.from_json(body)
    except client.exceptions.NoSuchKey:
        return None
    except Exception:
        log.warning("Failed to download state from S3 for %s", run_id)
        return None


def download_done_list(client, bucket: str, run_id: str, local_path: str) -> bool:
    """Download done list from S3. Returns True if successful."""
    key = done_s3_key(run_id)
    try:
        client.download_file(bucket, key, local_path)
        log.info("Done list downloaded from s3://%s/%s", bucket, key)
        return True
    except Exception:
        log.debug("No remote done list found for %s", run_id)
        return False

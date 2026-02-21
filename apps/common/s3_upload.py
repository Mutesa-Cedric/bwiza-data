"""S3 upload with idempotency, retries, multipart, and verification."""

import os
import time
from dataclasses import dataclass

from botocore.exceptions import ClientError

from apps.common.checksum import sha256_file
from apps.common.config_types import S3Config
from apps.common.logging import get_logger

log = get_logger(__name__)


@dataclass
class UploadResult:
    bucket: str
    key: str
    size: int
    etag: str = ""
    skipped: bool = False


def object_exists(client, bucket: str, key: str) -> tuple[bool, int | None]:
    """Check if an S3 object exists. Returns (exists, size_or_none)."""
    try:
        resp = client.head_object(Bucket=bucket, Key=key)
        return True, resp["ContentLength"]
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "404":
            return False, None
        raise


def upload_file(
    client,
    local_path: str,
    bucket: str,
    key: str,
    cfg: S3Config,
) -> UploadResult:
    """Upload a local file to S3 with idempotency check, retries, and multipart."""
    local_size = os.path.getsize(local_path)
    local_checksum = sha256_file(local_path)

    # Idempotent pre-check
    exists, remote_size = object_exists(client, bucket, key)
    if exists:
        if remote_size == local_size:
            log.info("Skip upload (already exists, size matches): %s", key)
            return UploadResult(bucket=bucket, key=key, size=local_size, skipped=True)
        raise ValueError(
            f"Object {key} exists with size {remote_size} but local is {local_size}. "
            "Refusing to overwrite."
        )

    # Configure multipart transfer
    from boto3.s3.transfer import TransferConfig

    transfer_cfg = TransferConfig(
        multipart_threshold=cfg.multipart_threshold_mb * 1024 * 1024,
        multipart_chunksize=cfg.multipart_chunk_mb * 1024 * 1024,
    )

    metadata = {"sha256": local_checksum}

    last_exc = None
    for attempt in range(1, cfg.max_retries + 1):
        try:
            client.upload_file(
                Filename=local_path,
                Bucket=bucket,
                Key=key,
                Config=transfer_cfg,
                ExtraArgs={"Metadata": metadata},
            )
            log.info("Uploaded %s (%d bytes, attempt %d)", key, local_size, attempt)
            break
        except ClientError as exc:
            last_exc = exc
            if attempt < cfg.max_retries:
                wait = cfg.retry_backoff_s * (2 ** (attempt - 1))
                log.warning(
                    "Upload attempt %d/%d failed for %s: %s. Retrying in %ds.",
                    attempt,
                    cfg.max_retries,
                    key,
                    exc,
                    wait,
                )
                time.sleep(wait)
            else:
                raise RuntimeError(
                    f"Upload failed after {cfg.max_retries} attempts: {key}"
                ) from last_exc

    return UploadResult(bucket=bucket, key=key, size=local_size)


def verify_upload(
    client,
    local_path: str,
    bucket: str,
    key: str,
) -> bool:
    """Verify a remote object matches local file size and sha256 metadata."""
    local_size = os.path.getsize(local_path)
    local_checksum = sha256_file(local_path)

    try:
        resp = client.head_object(Bucket=bucket, Key=key)
    except ClientError:
        log.error("Verification failed: object not found: %s", key)
        return False

    remote_size = resp["ContentLength"]
    if remote_size != local_size:
        log.error(
            "Size mismatch for %s: local=%d, remote=%d",
            key,
            local_size,
            remote_size,
        )
        return False

    remote_checksum = resp.get("Metadata", {}).get("sha256", "")
    if remote_checksum and remote_checksum != local_checksum:
        log.error(
            "Checksum mismatch for %s: local=%s, remote=%s",
            key,
            local_checksum,
            remote_checksum,
        )
        return False

    log.info("Verification passed for %s (%d bytes)", key, remote_size)
    return True

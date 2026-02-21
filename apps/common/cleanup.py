"""Safe post-upload cleanup of local shard files."""

from pathlib import Path

from apps.common.config_types import S3Config
from apps.common.logging import get_logger
from apps.common.s3_paths import shard_key
from apps.common.s3_upload import verify_upload

log = get_logger(__name__)


def cleanup_uploaded_shards(
    client,
    cfg: S3Config,
    run_id: str,
    manifest_entries: list[dict],
) -> dict:
    """Delete local shards that have been verified in S3.

    Only deletes .jsonl.zst files. Never deletes manifests or stats.
    Returns summary dict with counts.
    """
    if cfg.keep_local_after_upload:
        log.info("keep_local_after_upload is true, skipping cleanup")
        return {"deleted": 0, "kept": len(manifest_entries), "errors": []}

    deleted = 0
    kept = 0
    errors = []

    for entry in manifest_entries:
        local_path = entry["path"]
        if not Path(local_path).exists():
            kept += 1
            continue

        if not local_path.endswith(".jsonl.zst"):
            kept += 1
            continue

        key = shard_key(cfg.prefix, run_id, entry["filename"])

        if not verify_upload(client, local_path, cfg.bucket, key):
            errors.append(f"Verification failed, keeping: {local_path}")
            kept += 1
            continue

        try:
            Path(local_path).unlink()
            deleted += 1
            log.info("Deleted local shard: %s", local_path)
        except OSError as exc:
            errors.append(f"Failed to delete {local_path}: {exc}")
            kept += 1

    summary = {"deleted": deleted, "kept": kept, "errors": errors}
    log.info("Cleanup: deleted=%d, kept=%d, errors=%d", deleted, kept, len(errors))
    return summary

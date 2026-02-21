"""Upload a completed run (shards + manifest + stats) to S3."""

from pathlib import Path

from apps.common.config_types import AppConfig
from apps.common.logging import get_logger
from apps.common.manifest import read_manifest
from apps.common.s3_client import get_s3_client
from apps.common.s3_paths import manifest_key, shard_key, stats_key
from apps.common.s3_upload import UploadResult, upload_file, verify_upload

log = get_logger(__name__)


def upload_run(cfg: AppConfig, run_id: str) -> dict:
    """Upload all shards, manifest, and stats for a run. Returns summary dict."""
    s3cfg = cfg.s3
    client = get_s3_client(s3cfg)
    bucket = s3cfg.bucket
    prefix = s3cfg.prefix

    results: list[UploadResult] = []
    errors: list[str] = []

    # 1. Upload shards from manifest
    entries = read_manifest(run_id)
    if not entries:
        log.warning("No manifest entries for run_id=%s", run_id)

    for entry in entries:
        shard_path = entry["path"]
        if not Path(shard_path).exists():
            errors.append(f"Shard file missing: {shard_path}")
            continue

        key = shard_key(prefix, run_id, entry["filename"])
        try:
            result = upload_file(client, shard_path, bucket, key, s3cfg)
            results.append(result)

            if s3cfg.verify_after_upload and not result.skipped:
                if not verify_upload(client, shard_path, bucket, key):
                    errors.append(f"Verification failed: {key}")
        except Exception as exc:
            errors.append(f"Upload failed for {shard_path}: {exc}")

    # 2. Upload manifest
    if s3cfg.upload_manifests:
        manifest_path = Path("manifests/shards") / f"{run_id}.jsonl"
        if manifest_path.exists():
            key = manifest_key(prefix, run_id)
            try:
                result = upload_file(client, str(manifest_path), bucket, key, s3cfg)
                results.append(result)
            except Exception as exc:
                errors.append(f"Manifest upload failed: {exc}")
        else:
            log.warning("Manifest file not found: %s", manifest_path)

    # 3. Upload stats
    if s3cfg.upload_stats:
        stats_path = Path(cfg.output.local_dir) / run_id / "stats.json"
        if stats_path.exists():
            key = stats_key(prefix, run_id)
            try:
                result = upload_file(client, str(stats_path), bucket, key, s3cfg)
                results.append(result)
            except Exception as exc:
                errors.append(f"Stats upload failed: {exc}")
        else:
            log.warning("Stats file not found: %s", stats_path)

    uploaded = sum(1 for r in results if not r.skipped)
    skipped = sum(1 for r in results if r.skipped)
    total_bytes = sum(r.size for r in results)

    summary = {
        "run_id": run_id,
        "uploaded": uploaded,
        "skipped": skipped,
        "total_bytes": total_bytes,
        "errors": errors,
    }

    if errors:
        log.error("Upload completed with %d errors for run_id=%s", len(errors), run_id)
    else:
        log.info(
            "Upload complete for run_id=%s: %d uploaded, %d skipped, %d bytes",
            run_id,
            uploaded,
            skipped,
            total_bytes,
        )

    return summary

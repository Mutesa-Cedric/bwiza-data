"""Publish packaged dataset artifacts to S3."""

from dataclasses import dataclass, field
from pathlib import Path

from apps.common.config_types import S3Config
from apps.common.logging import get_logger
from apps.common.s3_upload import upload_file, verify_upload

log = get_logger(__name__)

DATASET_S3_PREFIX = "bwiza/datasets"


@dataclass
class PublishResult:
    """Summary of dataset publication."""

    uploaded: int = 0
    skipped: int = 0
    verified: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.failed == 0


def _dataset_key(version: str, dataset: str, filename: str) -> str:
    """Build S3 key for a dataset artifact."""
    return f"{DATASET_S3_PREFIX}/{version}/{dataset}/{filename}"


def publish_dataset(
    dataset: str,
    version: str,
    base_dir: str,
    s3_client,
    bucket: str,
    s3_cfg: S3Config,
    verify: bool = True,
) -> PublishResult:
    """Upload dataset artifacts (index, splits, stats, meta) to S3.

    base_dir should contain:
      index.jsonl
      splits/train.txt, splits/val.txt, splits/test.txt
      stats.json
      dataset_meta.json
    """
    base = Path(base_dir)
    result = PublishResult()

    # Files to upload: (local_relative_path, s3_filename)
    artifacts = [
        ("index.jsonl", "index.jsonl"),
        ("splits/train.txt", "splits/train.txt"),
        ("splits/val.txt", "splits/val.txt"),
        ("splits/test.txt", "splits/test.txt"),
        ("stats.json", "stats.json"),
        ("dataset_meta.json", "dataset_meta.json"),
    ]

    for local_rel, s3_name in artifacts:
        local_path = base / local_rel
        if not local_path.exists():
            log.warning("Artifact not found, skipping: %s", local_path)
            continue

        key = _dataset_key(version, dataset, s3_name)
        try:
            up_result = upload_file(s3_client, str(local_path), bucket, key, s3_cfg)
            if up_result.skipped:
                result.skipped += 1
            else:
                result.uploaded += 1

                if verify:
                    ok = verify_upload(s3_client, str(local_path), bucket, key)
                    if ok:
                        result.verified += 1
                    else:
                        result.failed += 1
                        result.errors.append(f"verification_failed: {key}")
        except Exception as exc:
            result.failed += 1
            result.errors.append(f"upload_failed: {key}: {exc}")
            log.exception("Failed to upload %s", key)

    log.info(
        "Publish %s/%s: uploaded=%d skipped=%d verified=%d failed=%d",
        dataset,
        version,
        result.uploaded,
        result.skipped,
        result.verified,
        result.failed,
    )
    return result

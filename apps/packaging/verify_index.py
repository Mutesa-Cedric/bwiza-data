"""Verify dataset index entries against S3 objects."""

from dataclasses import dataclass, field

from apps.common.dataset_index import DatasetIndexEntry, read_index
from apps.common.logging import get_logger

log = get_logger(__name__)


@dataclass
class VerifyResult:
    """Summary of index verification."""

    total: int = 0
    ok: int = 0
    missing: int = 0
    size_mismatch: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.missing == 0 and self.size_mismatch == 0


def verify_entry(entry: DatasetIndexEntry, s3_client, bucket: str) -> tuple[bool, str]:
    """Verify a single index entry exists in S3 with matching size."""
    try:
        resp = s3_client.head_object(Bucket=bucket, Key=entry.s3_key)
        actual_size = resp["ContentLength"]
        if actual_size != entry.bytes:
            return False, (
                f"size_mismatch: {entry.s3_key} expected={entry.bytes} actual={actual_size}"
            )
        return True, ""
    except s3_client.exceptions.NoSuchKey:
        return False, f"missing: {entry.s3_key}"
    except Exception as exc:
        return False, f"error: {entry.s3_key}: {exc}"


def verify_index(index_path: str, s3_client, bucket: str) -> VerifyResult:
    """Verify all entries in an index file against S3."""
    entries = read_index(index_path)
    result = VerifyResult(total=len(entries))

    for entry in entries:
        ok, reason = verify_entry(entry, s3_client, bucket)
        if ok:
            result.ok += 1
        else:
            if reason.startswith("missing:"):
                result.missing += 1
            elif reason.startswith("size_mismatch:"):
                result.size_mismatch += 1
            result.errors.append(reason)
            log.warning("Verify failed: %s", reason)

    log.info(
        "Verification: total=%d ok=%d missing=%d size_mismatch=%d",
        result.total,
        result.ok,
        result.missing,
        result.size_mismatch,
    )
    return result

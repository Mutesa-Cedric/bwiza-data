"""File checksum utilities."""

import hashlib


def sha256_file(path: str) -> str:
    """Compute SHA256 hex digest of a file without loading it fully into memory."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1 << 16):
            h.update(chunk)
    return h.hexdigest()

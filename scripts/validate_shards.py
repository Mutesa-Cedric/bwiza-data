#!/usr/bin/env python3
"""Validate a directory of zstd-compressed JSONL shards."""

import json
import sys
from pathlib import Path

import zstandard as zstd

from apps.common.checksum import sha256_file
from apps.common.token_estimate import estimate_tokens


def validate_shard(path: Path) -> dict:
    """Validate a single .jsonl.zst shard. Returns stats dict."""
    dctx = zstd.ZstdDecompressor()
    records = 0
    total_chars = 0
    errors = []

    try:
        with open(path, "rb") as f:
            reader = dctx.stream_reader(f)
            text_stream = reader.read()
        lines = text_stream.decode("utf-8").strip().split("\n")
        for i, line in enumerate(lines, 1):
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
                records += 1
                total_chars += len(obj.get("text", ""))
            except json.JSONDecodeError as exc:
                errors.append(f"Line {i}: {exc}")
    except Exception as exc:
        errors.append(f"Decompression error: {exc}")

    return {
        "filename": path.name,
        "records": records,
        "total_chars": total_chars,
        "token_estimate": estimate_tokens("x" * total_chars),
        "bytes": path.stat().st_size,
        "checksum": sha256_file(str(path)),
        "errors": errors,
    }


def main() -> int:
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <shard_dir>", file=sys.stderr)
        return 1

    shard_dir = Path(sys.argv[1])
    if not shard_dir.is_dir():
        print(f"Not a directory: {shard_dir}", file=sys.stderr)
        return 1

    shard_files = sorted(shard_dir.glob("*.jsonl.zst"))
    if not shard_files:
        print(f"No .jsonl.zst files found in {shard_dir}")
        return 1

    total_records = 0
    total_tokens = 0
    total_bytes = 0
    all_ok = True

    for path in shard_files:
        result = validate_shard(path)
        status = "OK" if not result["errors"] else "ERRORS"
        print(
            f"  {result['filename']}: {result['records']} records, "
            f"{result['bytes']} bytes - {status}"
        )
        if result["errors"]:
            all_ok = False
            for err in result["errors"]:
                print(f"    ERROR: {err}")
        total_records += result["records"]
        total_tokens += result["token_estimate"]
        total_bytes += result["bytes"]

    print("\n--- Summary ---")
    print(f"  Shards validated: {len(shard_files)}")
    print(f"  Total records: {total_records}")
    print(f"  Total bytes: {total_bytes}")
    print(f"  Token estimate: {total_tokens}")
    print(f"  Status: {'ALL OK' if all_ok else 'ERRORS FOUND'}")

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())

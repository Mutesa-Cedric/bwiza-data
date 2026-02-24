"""Pre-tokenized packed-sequence Parquet export for training."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

from apps.common.logging import get_logger
from apps.packaging.enrich import _extract_text, _iter_shard_docs, _resolve_shard_path

log = get_logger(__name__)


def _pack_sequences(
    docs: list[dict],
    tokenizer: object,
    eos_token_id: int,
    max_length: int = 4096,
) -> Iterator[list[int]]:
    """Pack tokenized documents into fixed-length sequences.

    Concatenates token IDs from multiple documents with EOS separators.
    Yields sequences of exactly max_length tokens, except possibly the
    last one which may be shorter (no padding).
    """
    buffer: list[int] = []

    for doc in docs:
        text = _extract_text(doc)
        if not text:
            continue

        token_ids = tokenizer.encode(text)  # type: ignore[union-attr]
        if not token_ids:
            continue

        # Add EOS separator between documents
        if buffer:
            buffer.append(eos_token_id)

        buffer.extend(token_ids)

        # Yield complete sequences
        while len(buffer) >= max_length:
            yield buffer[:max_length]
            buffer = buffer[max_length:]

    # Yield remaining tokens (no padding)
    if buffer:
        yield buffer


def export_split_to_parquet(
    split_file: str | Path,
    shard_dir: str,
    output_path: str | Path,
    tokenizer_name: str = "Qwen/Qwen3-8B",
    max_length: int = 4096,
) -> dict:
    """Export a split file to pre-tokenized packed Parquet.

    Args:
        split_file: Path to split file (one S3 key per line).
        shard_dir: Local directory containing shard files.
        output_path: Output Parquet file path.
        tokenizer_name: HuggingFace tokenizer name.
        max_length: Maximum sequence length for packing.

    Returns:
        Dict with export statistics.
    """
    import pyarrow as pa  # type: ignore[import-untyped]
    import pyarrow.parquet as pq  # type: ignore[import-untyped]
    from transformers import AutoTokenizer  # type: ignore[import-untyped]

    from apps.common.dataset_index import DatasetIndexEntry

    split_path = Path(split_file)
    if not split_path.exists():
        raise FileNotFoundError(f"Split file not found: {split_path}")

    s3_keys = [line.strip() for line in split_path.read_text().splitlines() if line.strip()]
    if not s3_keys:
        log.warning("Empty split file: %s", split_path)
        return {"sequences": 0, "total_tokens": 0}

    log.info("Loading tokenizer: %s", tokenizer_name)
    tokenizer = AutoTokenizer.from_pretrained(tokenizer_name, trust_remote_code=True)
    eos_token_id = tokenizer.eos_token_id
    if eos_token_id is None:
        eos_token_id = tokenizer.convert_tokens_to_ids("</s>")
        log.warning("No eos_token_id, falling back to </s>: %d", eos_token_id)

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    schema = pa.schema(
        [
            pa.field("input_ids", pa.list_(pa.int32())),
            pa.field("length", pa.int32()),
        ]
    )

    total_sequences = 0
    total_tokens = 0
    shards_processed = 0
    shards_skipped = 0

    writer = pq.ParquetWriter(str(out), schema)
    try:
        for s3_key in s3_keys:
            # Create a minimal entry to resolve shard path
            shard_name = s3_key.split("/")[-1]
            entry = DatasetIndexEntry(
                dataset="",
                version="",
                run_id="",
                source="",
                shard_name=shard_name,
                s3_bucket="",
                s3_key=s3_key,
                bytes=0,
                records=0,
                token_estimate=0,
                checksum_sha256="",
                created_at="",
            )

            shard_path = _resolve_shard_path(entry, shard_dir)
            if shard_path is None:
                shards_skipped += 1
                log.warning("Shard not found: %s", shard_name)
                continue

            docs = _iter_shard_docs(shard_path)
            shards_processed += 1

            for seq in _pack_sequences(docs, tokenizer, eos_token_id, max_length):
                batch = pa.record_batch(
                    [
                        pa.array([seq], type=pa.list_(pa.int32())),
                        pa.array([len(seq)], type=pa.int32()),
                    ],
                    schema=schema,
                )
                writer.write_batch(batch)
                total_sequences += 1
                total_tokens += len(seq)

            if shards_processed % 10 == 0:
                log.info(
                    "Progress: %d shards, %d sequences, %d tokens",
                    shards_processed,
                    total_sequences,
                    total_tokens,
                )
    finally:
        writer.close()

    stats = {
        "split_file": str(split_file),
        "output": str(out),
        "shards_processed": shards_processed,
        "shards_skipped": shards_skipped,
        "sequences": total_sequences,
        "total_tokens": total_tokens,
        "max_length": max_length,
    }
    log.info(
        "Export complete: %d sequences, %d tokens from %d shards → %s",
        total_sequences,
        total_tokens,
        shards_processed,
        out,
    )
    return stats


def export_all_splits(
    splits_dir: str | Path,
    shard_dir: str,
    output_dir: str | Path,
    tokenizer_name: str = "Qwen/Qwen3-8B",
    max_length: int = 4096,
) -> dict:
    """Export all splits (train/val/test) to Parquet files.

    Args:
        splits_dir: Directory containing train.txt, val.txt, test.txt.
        shard_dir: Local directory containing shard files.
        output_dir: Output directory for Parquet files.
        tokenizer_name: HuggingFace tokenizer name.
        max_length: Maximum sequence length for packing.

    Returns:
        Dict mapping split name to export statistics.
    """
    splits_path = Path(splits_dir)
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    results = {}
    for split_name in ("train", "val", "test"):
        split_file = splits_path / f"{split_name}.txt"
        if not split_file.exists():
            log.warning("Split file not found: %s", split_file)
            continue

        output_parquet = out_path / f"{split_name}.parquet"
        stats = export_split_to_parquet(
            split_file=str(split_file),
            shard_dir=shard_dir,
            output_path=str(output_parquet),
            tokenizer_name=tokenizer_name,
            max_length=max_length,
        )
        results[split_name] = stats

    # Write summary
    summary_path = out_path / "export_summary.json"
    with open(summary_path, "w") as f:
        json.dump(results, f, indent=2)
    log.info("Export summary written to %s", summary_path)

    return results

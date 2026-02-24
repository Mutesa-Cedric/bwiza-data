"""Gate G2: Token calibration with Qwen3-8B tokenizer.

Measure real chars/token ratio on existing corpus to calibrate token estimation.
Kinyarwanda is agglutinative, so BPE over-splits → fewer chars/token → more
tokens per character than English.

Usage:
    python scripts/gate_token_calibration.py [--max-docs-per-source 1000]
"""

import argparse
import json
import time
from pathlib import Path

import orjson
import zstandard as zstd

from apps.common.logging import get_logger, setup_logging
from apps.common.token_estimate import _TEXT_FIELDS, CHARS_PER_TOKEN

log = get_logger(__name__)

SHARD_DIR = Path("outputs/shards")


def _read_shard_docs(shard_path: Path, max_docs: int) -> list[dict]:
    """Read up to max_docs from a zstd-compressed JSONL shard."""
    docs = []
    dctx = zstd.ZstdDecompressor()
    with open(shard_path, "rb") as f:
        with dctx.stream_reader(f) as reader:
            buf = b""
            while len(docs) < max_docs:
                chunk = reader.read(65536)
                if not chunk:
                    break
                buf += chunk
                while b"\n" in buf and len(docs) < max_docs:
                    line, buf = buf.split(b"\n", 1)
                    if line.strip():
                        docs.append(orjson.loads(line))
    return docs


def _extract_text(doc: dict) -> str:
    """Extract text content from a document dict."""
    for key in _TEXT_FIELDS:
        if key in doc and isinstance(doc[key], str) and doc[key].strip():
            return doc[key]
    # Fallback: concatenate all string fields
    parts = []
    for v in doc.values():
        if isinstance(v, str) and len(v) > 50:
            parts.append(v)
    return " ".join(parts)


def _find_shards_by_source() -> dict[str, list[Path]]:
    """Find all shard files grouped by source type."""
    sources = {}
    for shard_path in SHARD_DIR.rglob("*.jsonl.zst"):
        name = shard_path.name
        # Extract source from filename: bwiza_{source}_{runid}_part-N.jsonl.zst
        parts = name.split("_")
        if len(parts) >= 3:
            # source is between first and last known parts
            # bwiza_commoncrawl_20260221T053814Z_part-000001.jsonl.zst
            # bwiza_targeted_web_20260221T053814Z_part-000001.jsonl.zst
            source = "_".join(parts[1:-2])  # everything between bwiza_ and _TIMESTAMP
        else:
            source = "unknown"
        sources.setdefault(source, []).append(shard_path)
    return sources


def _compute_stats(ratios: list[float]) -> dict:
    """Compute distribution stats from a list of ratios."""
    if not ratios:
        return {}
    sorted_r = sorted(ratios)
    n = len(sorted_r)
    return {
        "count": n,
        "min": round(sorted_r[0], 4),
        "p5": round(sorted_r[max(0, n // 20)], 4),
        "p25": round(sorted_r[n // 4], 4),
        "median": round(sorted_r[n // 2], 4),
        "p75": round(sorted_r[3 * n // 4], 4),
        "p95": round(sorted_r[min(n - 1, 19 * n // 20)], 4),
        "max": round(sorted_r[-1], 4),
        "mean": round(sum(sorted_r) / n, 4),
    }


def main():
    parser = argparse.ArgumentParser(description="Gate G2: Token calibration")
    parser.add_argument(
        "--max-docs-per-source", type=int, default=1000, help="Max docs per source"
    )
    parser.add_argument("--tokenizer", default="Qwen/Qwen3-8B", help="HF tokenizer name")
    args = parser.parse_args()

    setup_logging("INFO")

    # Load tokenizer
    log.info("Loading tokenizer: %s", args.tokenizer)
    try:
        from transformers import AutoTokenizer  # type: ignore[import-untyped]

        tokenizer = AutoTokenizer.from_pretrained(args.tokenizer, trust_remote_code=True)
    except ImportError:
        log.error("transformers not installed. Run: pip install transformers")
        raise SystemExit(1)
    except Exception as exc:
        log.error("Failed to load tokenizer %s: %s", args.tokenizer, exc)
        raise SystemExit(1)

    unk_token_id = tokenizer.unk_token_id
    log.info(
        "Tokenizer loaded. Vocab size: %d, unk_token_id: %s", tokenizer.vocab_size, unk_token_id
    )

    # Find shards
    sources = _find_shards_by_source()
    if not sources:
        log.error("No shards found in %s", SHARD_DIR)
        raise SystemExit(1)

    log.info("Found sources: %s", list(sources.keys()))

    start_time = time.time()
    per_source_results = {}
    all_ratios = []

    for source, shard_paths in sorted(sources.items()):
        log.info("--- Source: %s (%d shards) ---", source, len(shard_paths))

        docs = []
        for sp in shard_paths:
            remaining = args.max_docs_per_source - len(docs)
            if remaining <= 0:
                break
            docs.extend(_read_shard_docs(sp, remaining))

        log.info("  Loaded %d docs", len(docs))

        chars_per_token_ratios = []
        unk_counts = []
        total_tokens = 0
        total_unk = 0
        total_chars = 0
        encoding_errors = 0

        for doc in docs:
            text = _extract_text(doc)
            if not text or len(text) < 50:
                continue

            try:
                token_ids = tokenizer.encode(text)
            except Exception:
                encoding_errors += 1
                continue

            n_tokens = len(token_ids)
            if n_tokens == 0:
                continue

            n_chars = len(text)
            ratio = n_chars / n_tokens
            chars_per_token_ratios.append(ratio)
            all_ratios.append(ratio)

            total_tokens += n_tokens
            total_chars += n_chars

            if unk_token_id is not None:
                n_unk = token_ids.count(unk_token_id)
                total_unk += n_unk
                if n_tokens > 0:
                    unk_counts.append(n_unk / n_tokens)

        unk_rate = total_unk / total_tokens if total_tokens else 0

        per_source_results[source] = {
            "docs_sampled": len(docs),
            "docs_tokenized": len(chars_per_token_ratios),
            "encoding_errors": encoding_errors,
            "total_tokens": total_tokens,
            "total_chars": total_chars,
            "total_unk_tokens": total_unk,
            "unk_rate": round(unk_rate, 6),
            "unk_rate_pct": f"{unk_rate * 100:.4f}%",
            "chars_per_token": _compute_stats(chars_per_token_ratios),
            "current_estimate_tokens": int(total_chars / CHARS_PER_TOKEN),
            "real_tokens": total_tokens,
            "estimation_error_pct": (
                f"{((total_chars / CHARS_PER_TOKEN) - total_tokens) / total_tokens * 100:.1f}%"
                if total_tokens
                else "N/A"
            ),
        }

        log.info(
            "  chars/token: median=%.2f, mean=%.2f, unk_rate=%.4f%%",
            per_source_results[source]["chars_per_token"].get("median", 0),
            per_source_results[source]["chars_per_token"].get("mean", 0),
            unk_rate * 100,
        )

    # Global stats
    global_stats = _compute_stats(all_ratios)
    recommended_constant = global_stats.get("median", 4.0) if global_stats else 4.0

    report = {
        "gate": "G2",
        "description": "Token calibration — measure real chars/token for Kinyarwanda",
        "tokenizer": args.tokenizer,
        "start_time": start_time,
        "end_time": time.time(),
        "elapsed_s": round(time.time() - start_time, 2),
        "global_chars_per_token": global_stats,
        "current_constant": CHARS_PER_TOKEN,
        "recommended_constant": round(recommended_constant, 2),
        "estimation_direction": (
            f"UNDERESTIMATE (current len/{CHARS_PER_TOKEN} produces fewer tokens than real)"
            if recommended_constant < CHARS_PER_TOKEN
            else f"OVERESTIMATE (current len/{CHARS_PER_TOKEN} produces more tokens than real)"
        ),
        "per_source": per_source_results,
        "action_items": [
            (
                "Update CHARS_PER_TOKEN in apps/common/token_estimate.py"
                f" from {CHARS_PER_TOKEN} to {round(recommended_constant, 2)}"
            ),
            (
                "shard_writer.py calls estimate_tokens_from_doc()"
                " — existing ShardMeta retains old estimates"
            ),
            "Re-index existing shards after calibration",
        ],
    }

    # Write report
    out_dir = Path("outputs/gate_checks")
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / "token_calibration_report.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)

    log.info("=" * 60)
    log.info("GATE G2 RESULTS")
    log.info("=" * 60)
    log.info("Tokenizer: %s", args.tokenizer)
    log.info(
        "Global chars/token: median=%.2f, mean=%.2f",
        global_stats.get("median", 0),
        global_stats.get("mean", 0),
    )
    log.info("Current constant: %.2f", CHARS_PER_TOKEN)
    log.info("Recommended constant: %.2f", recommended_constant)
    log.info("Direction: %s", report["estimation_direction"])
    for source, res in per_source_results.items():
        log.info(
            "  %s: docs=%d, unk_rate=%s, chars/tok=%.2f",
            source,
            res["docs_tokenized"],
            res["unk_rate_pct"],
            res["chars_per_token"].get("median", 0),
        )
    log.info("Report written to %s", report_path)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Tokenizer validation report for training readiness.

Samples documents per source, computes:
- Unknown token rate (UNK%)
- Tokens per character ratio
- Vocabulary coverage
- Flags sources where unk_rate > threshold (default 1%)

Usage:
    python scripts/tokenizer_validation.py \
        --shard-dir outputs/shards \
        --tokenizer Qwen/Qwen3-8B \
        --max-docs-per-source 500
"""

import argparse
import json
import time
from pathlib import Path

import orjson
import zstandard as zstd

from apps.common.logging import get_logger, setup_logging
from apps.common.token_estimate import CHARS_PER_TOKEN

log = get_logger(__name__)

SHARD_DIR = Path("outputs/shards")

# Text fields to check in document dicts (priority order)
_TEXT_FIELDS = ("text", "rw_text", "en_text", "prompt", "response")


def _read_shard_docs(shard_path: Path, max_docs: int) -> list[dict]:
    """Read up to max_docs from a zstd-compressed JSONL shard."""
    docs: list[dict] = []
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
    parts = []
    for v in doc.values():
        if isinstance(v, str) and len(v) > 50:
            parts.append(v)
    return " ".join(parts)


def _find_shards_by_source(shard_dir: Path) -> dict[str, list[Path]]:
    """Find all shard files grouped by source type."""
    sources: dict[str, list[Path]] = {}
    for shard_path in shard_dir.rglob("*.jsonl.zst"):
        name = shard_path.name
        parts = name.split("_")
        if len(parts) >= 3:
            source = "_".join(parts[1:-2])
        else:
            source = "unknown"
        sources.setdefault(source, []).append(shard_path)
    return sources


def _compute_stats(values: list[float]) -> dict:
    """Compute distribution stats from a list of values."""
    if not values:
        return {}
    s = sorted(values)
    n = len(s)
    return {
        "count": n,
        "min": round(s[0], 4),
        "p5": round(s[max(0, n // 20)], 4),
        "p25": round(s[n // 4], 4),
        "median": round(s[n // 2], 4),
        "p75": round(s[3 * n // 4], 4),
        "p95": round(s[min(n - 1, 19 * n // 20)], 4),
        "max": round(s[-1], 4),
        "mean": round(sum(s) / n, 4),
    }


def _compute_source_report(
    source: str,
    docs: list[dict],
    tokenizer: object,
    unk_token_id: int | None,
) -> dict:
    """Compute per-source validation metrics."""
    chars_per_token_ratios: list[float] = []
    total_tokens = 0
    total_unk = 0
    total_chars = 0
    encoding_errors = 0
    unique_token_ids: set[int] = set()

    for doc in docs:
        text = _extract_text(doc)
        if not text or len(text) < 50:
            continue

        try:
            token_ids = tokenizer.encode(text)  # type: ignore[union-attr]
        except Exception:
            encoding_errors += 1
            continue

        n_tokens = len(token_ids)
        if n_tokens == 0:
            continue

        n_chars = len(text)
        ratio = n_chars / n_tokens
        chars_per_token_ratios.append(ratio)

        total_tokens += n_tokens
        total_chars += n_chars
        unique_token_ids.update(token_ids)

        if unk_token_id is not None:
            total_unk += token_ids.count(unk_token_id)

    unk_rate = total_unk / total_tokens if total_tokens else 0
    vocab_size = getattr(tokenizer, "vocab_size", 0)
    vocab_coverage = len(unique_token_ids) / vocab_size if vocab_size else 0

    return {
        "source": source,
        "docs_sampled": len(docs),
        "docs_tokenized": len(chars_per_token_ratios),
        "encoding_errors": encoding_errors,
        "total_tokens": total_tokens,
        "total_chars": total_chars,
        "total_unk_tokens": total_unk,
        "unk_rate": round(unk_rate, 6),
        "unk_rate_pct": f"{unk_rate * 100:.4f}%",
        "vocab_coverage": round(vocab_coverage, 4),
        "unique_tokens_used": len(unique_token_ids),
        "chars_per_token": _compute_stats(chars_per_token_ratios),
        "current_estimate_tokens": int(total_chars / CHARS_PER_TOKEN) if total_chars else 0,
        "real_tokens": total_tokens,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Tokenizer validation report")
    parser.add_argument(
        "--shard-dir",
        default=str(SHARD_DIR),
        help="Local shard directory",
    )
    parser.add_argument(
        "--tokenizer",
        default="Qwen/Qwen3-8B",
        help="HuggingFace tokenizer name",
    )
    parser.add_argument(
        "--max-docs-per-source",
        type=int,
        default=500,
        help="Max docs to sample per source",
    )
    parser.add_argument(
        "--unk-threshold",
        type=float,
        default=0.01,
        help="UNK rate threshold for flagging (default 1%%)",
    )
    parser.add_argument(
        "--output",
        default="outputs/gate_checks/tokenizer_validation_report.json",
        help="Output report path",
    )
    args = parser.parse_args()

    setup_logging("INFO")
    start_time = time.time()

    # Load tokenizer
    log.info("Loading tokenizer: %s", args.tokenizer)
    try:
        from transformers import AutoTokenizer  # type: ignore[import-untyped]

        tokenizer = AutoTokenizer.from_pretrained(args.tokenizer, trust_remote_code=True)
    except ImportError:
        log.error("transformers not installed. Run: pip install transformers")
        return 1
    except Exception as exc:
        log.error("Failed to load tokenizer %s: %s", args.tokenizer, exc)
        return 1

    unk_token_id = tokenizer.unk_token_id
    log.info(
        "Tokenizer loaded. Vocab size: %d, unk_token_id: %s",
        tokenizer.vocab_size,
        unk_token_id,
    )

    # Find shards
    shard_dir = Path(args.shard_dir)
    sources = _find_shards_by_source(shard_dir)
    if not sources:
        log.error("No shards found in %s", shard_dir)
        return 1

    log.info("Found sources: %s", list(sources.keys()))

    per_source_results: dict[str, dict] = {}
    flagged_sources: list[str] = []

    for source, shard_paths in sorted(sources.items()):
        log.info("--- Source: %s (%d shards) ---", source, len(shard_paths))

        docs: list[dict] = []
        for sp in shard_paths:
            remaining = args.max_docs_per_source - len(docs)
            if remaining <= 0:
                break
            docs.extend(_read_shard_docs(sp, remaining))

        log.info("  Loaded %d docs", len(docs))

        report = _compute_source_report(source, docs, tokenizer, unk_token_id)
        per_source_results[source] = report

        unk_rate = report["unk_rate"]
        if unk_rate > args.unk_threshold:
            flagged_sources.append(source)
            log.warning(
                "  FLAGGED: unk_rate=%.4f%% exceeds threshold %.4f%%",
                unk_rate * 100,
                args.unk_threshold * 100,
            )
        else:
            log.info(
                "  OK: unk_rate=%s, chars/token median=%.2f",
                report["unk_rate_pct"],
                report["chars_per_token"].get("median", 0),
            )

    # Build report
    report = {
        "gate": "tokenizer_validation",
        "description": "Tokenizer readiness validation for training",
        "tokenizer": args.tokenizer,
        "unk_threshold": args.unk_threshold,
        "start_time": start_time,
        "end_time": time.time(),
        "elapsed_s": round(time.time() - start_time, 2),
        "pass": len(flagged_sources) == 0,
        "flagged_sources": flagged_sources,
        "per_source": per_source_results,
    }

    # Write report
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        json.dump(report, f, indent=2)

    log.info("=" * 60)
    log.info("TOKENIZER VALIDATION RESULTS")
    log.info("=" * 60)
    log.info("Tokenizer: %s", args.tokenizer)
    log.info("Pass: %s", "YES" if report["pass"] else "NO")
    if flagged_sources:
        log.warning(
            "Flagged sources (unk > %.1f%%): %s", args.unk_threshold * 100, flagged_sources
        )
    for source, res in per_source_results.items():
        log.info(
            "  %s: docs=%d, unk=%s, chars/tok=%.2f, coverage=%.2f%%",
            source,
            res["docs_tokenized"],
            res["unk_rate_pct"],
            res["chars_per_token"].get("median", 0),
            res["vocab_coverage"] * 100,
        )
    log.info("Report written to %s", out)

    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

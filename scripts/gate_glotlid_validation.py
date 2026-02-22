"""Gate G3: GlotLID precision/recall validation for Kinyarwanda.

Sample docs from targeted crawler shards, run predict(text, k=2) to get
top-2 language predictions, and export for manual labeling. After labeling,
compute precision/recall and Kirundi confusion rate.

Usage:
    # Step 1: Export samples for labeling
    python scripts/gate_glotlid_validation.py export [--num-samples 200]

    # Step 2: After manual labeling, compute metrics
    python scripts/gate_glotlid_validation.py evaluate
"""

import argparse
import json
import random
import time
from pathlib import Path

import orjson
import zstandard as zstd

import apps.common.lid as lid_module
from apps.common.lid import _load_model
from apps.common.logging import get_logger, setup_logging
from apps.common.normalize import normalize_text

log = get_logger(__name__)

SHARD_DIR = Path("outputs/shards")
OUT_DIR = Path("outputs/gate_checks/glotlid_labels")


def _predict_top2(text: str) -> list[tuple[str, float]]:
    """Run GlotLID with k=2, return [(lang, score), (lang, score)]."""
    _load_model()
    model = lid_module._model
    assert model is not None
    clean = text.replace("\n", " ")[:5000]
    predictions = model.predict(clean, k=2)
    results = []
    for i in range(min(2, len(predictions[0]))):
        label = predictions[0][i].replace("__label__", "")  # type: ignore[union-attr]
        score = float(predictions[1][i])
        results.append((label, score))
    return results


def _read_targeted_docs(max_docs: int) -> list[dict]:
    """Read docs from targeted crawler shards."""
    docs = []
    for shard_path in SHARD_DIR.rglob("*targeted_web*.jsonl.zst"):
        if len(docs) >= max_docs:
            break
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


def _get_domain(url: str) -> str:
    """Extract domain from URL."""
    try:
        from urllib.parse import urlparse

        return urlparse(url).netloc.lower().removeprefix("www.")
    except Exception:
        return "unknown"


def cmd_export(args):
    """Export samples with k=2 predictions for manual labeling."""
    setup_logging("INFO")
    log.info("Loading docs from targeted crawler shards...")

    all_docs = _read_targeted_docs(max_docs=5000)
    log.info("Loaded %d docs total", len(all_docs))

    if not all_docs:
        log.error("No targeted crawler docs found in %s", SHARD_DIR)
        raise SystemExit(1)

    # Stratified sampling by domain
    by_domain: dict[str, list[dict]] = {}
    for doc in all_docs:
        domain = _get_domain(doc.get("url", ""))
        by_domain.setdefault(domain, []).append(doc)

    log.info("Domains found: %s", {d: len(v) for d, v in by_domain.items()})

    # Sample proportionally from each domain
    samples = []
    total_available = len(all_docs)
    rng = random.Random(42)

    for domain, domain_docs in sorted(by_domain.items()):
        proportion = len(domain_docs) / total_available
        n_sample = max(1, round(args.num_samples * proportion))
        chosen = rng.sample(domain_docs, min(n_sample, len(domain_docs)))
        samples.extend(chosen)

    # Trim to requested size
    if len(samples) > args.num_samples:
        rng.shuffle(samples)
        samples = samples[: args.num_samples]

    log.info("Sampled %d docs across %d domains", len(samples), len(by_domain))

    # Run k=2 predictions
    labeled_samples = []
    for i, doc in enumerate(samples):
        text = doc.get("text", "")
        normalized = normalize_text(text)
        top2 = _predict_top2(normalized)

        entry = {
            "sample_id": i + 1,
            "url": doc.get("url", ""),
            "domain": _get_domain(doc.get("url", "")),
            "text_preview": normalized[:500],
            "text_length": len(normalized),
            "predicted_lang_1": top2[0][0] if len(top2) > 0 else "",
            "score_1": top2[0][1] if len(top2) > 0 else 0.0,
            "predicted_lang_2": top2[1][0] if len(top2) > 1 else "",
            "score_2": top2[1][1] if len(top2) > 1 else 0.0,
            "confidence_gap": (round(top2[0][1] - top2[1][1], 4) if len(top2) > 1 else 0.0),
            "human_label": "",  # TO BE FILLED MANUALLY
        }
        labeled_samples.append(entry)

    # Write export file
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    export_path = OUT_DIR / "samples_for_labeling.jsonl"
    with open(export_path, "w") as f:
        for entry in labeled_samples:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # Also write a summary of predictions
    lang1_dist = {}
    lang2_dist = {}
    for entry in labeled_samples:
        lang1_dist[entry["predicted_lang_1"]] = lang1_dist.get(entry["predicted_lang_1"], 0) + 1
        if entry["predicted_lang_2"]:
            lang2_dist[entry["predicted_lang_2"]] = (
                lang2_dist.get(entry["predicted_lang_2"], 0) + 1
            )

    summary = {
        "total_samples": len(labeled_samples),
        "domains_sampled": list({e["domain"] for e in labeled_samples}),
        "predicted_lang_1_distribution": dict(sorted(lang1_dist.items(), key=lambda x: -x[1])),
        "predicted_lang_2_distribution": dict(sorted(lang2_dist.items(), key=lambda x: -x[1])),
        "mean_confidence_gap": (
            round(
                sum(e["confidence_gap"] for e in labeled_samples) / len(labeled_samples),
                4,
            )
            if labeled_samples
            else 0
        ),
    }

    summary_path = OUT_DIR / "prediction_summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    log.info("Exported %d samples to %s", len(labeled_samples), export_path)
    log.info("Prediction summary: %s", summary_path)
    log.info(
        "Next: Open %s, fill 'human_label' with 'kin', 'run', or 'other'."
        " Then run: python scripts/gate_glotlid_validation.py evaluate",
        export_path,
    )


def cmd_evaluate(args):
    """Compute precision/recall from manually labeled samples."""
    setup_logging("INFO")

    labeled_path = OUT_DIR / "samples_for_labeling.jsonl"
    if not labeled_path.exists():
        log.error("Labeled file not found: %s. Run 'export' first.", labeled_path)
        raise SystemExit(1)

    samples = []
    with open(labeled_path) as f:
        for line in f:
            if line.strip():
                samples.append(json.loads(line))

    # Check labeling completeness
    labeled = [s for s in samples if s.get("human_label")]
    unlabeled = len(samples) - len(labeled)
    if unlabeled > 0:
        log.warning("%d of %d samples not yet labeled", unlabeled, len(samples))
    if not labeled:
        log.error("No samples have been labeled yet. Fill 'human_label' field first.")
        raise SystemExit(1)

    log.info("Evaluating %d labeled samples", len(labeled))

    # Compute metrics
    tp = 0  # GlotLID says kin_Latn AND human says kin
    fp = 0  # GlotLID says kin_Latn BUT human says NOT kin
    fn = 0  # GlotLID says NOT kin_Latn BUT human says kin
    tn = 0  # GlotLID says NOT kin_Latn AND human says NOT kin

    kirundi_as_second = 0
    kirundi_confusion_gaps = []

    for s in labeled:
        predicted_rw = s["predicted_lang_1"] in {"kin_Latn", "rw"}
        actually_rw = s["human_label"] == "kin"

        if predicted_rw and actually_rw:
            tp += 1
        elif predicted_rw and not actually_rw:
            fp += 1
        elif not predicted_rw and actually_rw:
            fn += 1
        else:
            tn += 1

        # Kirundi confusion analysis
        if s["predicted_lang_2"] == "run_Latn":
            kirundi_as_second += 1
            kirundi_confusion_gaps.append(s["confidence_gap"])

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

    kirundi_rate = kirundi_as_second / len(labeled) if labeled else 0
    mean_kirundi_gap = (
        sum(kirundi_confusion_gaps) / len(kirundi_confusion_gaps) if kirundi_confusion_gaps else 0
    )

    # Kirundi inclusion analysis
    kirundi_labeled = [s for s in labeled if s["human_label"] == "run"]
    actually_kirundi = len(kirundi_labeled)

    report = {
        "gate": "G3",
        "description": "GlotLID precision/recall for Kinyarwanda",
        "timestamp": time.time(),
        "total_labeled": len(labeled),
        "unlabeled": unlabeled,
        "confusion_matrix": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "kirundi_analysis": {
            "run_Latn_as_second_prediction": kirundi_as_second,
            "kirundi_as_second_rate": round(kirundi_rate, 4),
            "mean_confidence_gap_when_kirundi_second": round(mean_kirundi_gap, 4),
            "docs_labeled_as_kirundi": actually_kirundi,
        },
        "kirundi_decision": "",  # TO BE FILLED after reviewing results
        "label_distribution": {
            "kin": sum(1 for s in labeled if s["human_label"] == "kin"),
            "run": actually_kirundi,
            "other": sum(1 for s in labeled if s["human_label"] not in {"kin", "run"}),
        },
    }

    # Auto-suggest decision
    if actually_kirundi > len(labeled) * 0.05:
        report["kirundi_suggestion"] = (
            f"INCLUDE — {actually_kirundi} docs ({actually_kirundi / len(labeled) * 100:.1f}%) "
            "are Kirundi. Given mutual intelligibility, including Kirundi "
            "expands the corpus with minimal quality risk."
        )
    else:
        report["kirundi_suggestion"] = (
            f"EXCLUDE — only {actually_kirundi} docs labeled Kirundi. "
            "Not enough to justify the complexity of dual-language support."
        )

    report_path = OUT_DIR / "glotlid_validation_report.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    log.info("=" * 60)
    log.info("GATE G3 RESULTS")
    log.info("=" * 60)
    log.info("Samples labeled: %d", len(labeled))
    log.info("Precision: %.4f", precision)
    log.info("Recall: %.4f", recall)
    log.info("F1: %.4f", f1)
    log.info("Kirundi as 2nd prediction: %d (%.1f%%)", kirundi_as_second, kirundi_rate * 100)
    log.info("Docs labeled as Kirundi: %d", actually_kirundi)
    log.info("Suggestion: %s", report["kirundi_suggestion"])
    log.info("Report written to %s", report_path)


def main():
    parser = argparse.ArgumentParser(description="Gate G3: GlotLID validation")
    subparsers = parser.add_subparsers(dest="command", required=True)

    export_parser = subparsers.add_parser("export", help="Export samples for labeling")
    export_parser.add_argument("--num-samples", type=int, default=200, help="Number of samples")

    subparsers.add_parser("evaluate", help="Evaluate labeled samples")

    args = parser.parse_args()
    if args.command == "export":
        cmd_export(args)
    elif args.command == "evaluate":
        cmd_evaluate(args)


if __name__ == "__main__":
    main()

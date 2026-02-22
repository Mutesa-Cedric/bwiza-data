"""Gate G1: CC yield validation experiment.

Re-run CC miner on WET files with lowered GlotLID threshold to determine if
low yield (0.00088%) is real scarcity or over-filtering. Logs language label
distribution at multiple thresholds.

Usage:
    python scripts/gate_cc_yield.py [--max-wet-files 50] [--config configs/default.yaml]
"""

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

from apps.cc_miner.decompress import iter_text_lines
from apps.cc_miner.http_stream import stream_download
from apps.cc_miner.wet_parser import parse_wet
from apps.common.config import load_config
from apps.common.filters.base import run_filters
from apps.common.filters.purity import required_confidence_for_length
from apps.common.filters.quality import register_quality_filters
from apps.common.lid import predict_lang
from apps.common.logging import get_logger, setup_logging
from apps.common.normalize import normalize_text

log = get_logger(__name__)

# Thresholds to test
THRESHOLDS = [0.50, 0.65, 0.80]


def _process_wet(wet_url, cfg, results):
    """Process one WET file and collect label distribution + threshold yields."""
    log.info("Processing WET: %s", wet_url)
    wet_labels = Counter()
    wet_docs_seen = 0
    wet_scores_by_threshold = {t: {"kept": 0, "scores": []} for t in THRESHOLDS}

    try:
        byte_chunks = stream_download(wet_url, cfg)
        lines = iter_text_lines(byte_chunks)
    except Exception as exc:
        log.error("Failed to download %s: %s", wet_url, exc)
        results["failed_wets"].append({"url": wet_url, "error": str(exc)})
        return

    for record in parse_wet(lines):
        wet_docs_seen += 1
        results["total_docs_seen"] += 1

        text = normalize_text(record.text)
        if len(text) < cfg.filters.min_chars:
            results["reject_reasons"]["reject.too_short"] += 1
            continue

        lang, score, _model = predict_lang(text)
        wet_labels[lang] += 1
        results["global_labels"][lang] += 1

        # Check if this is Kinyarwanda at each threshold
        if lang not in {"kin_Latn", "rw"}:
            results["reject_reasons"]["reject.lid.not_rw"] += 1
            continue

        # Record score for Kinyarwanda-labeled docs
        results["rw_scores"].append(round(score, 4))

        # Run quality filters once (same for all thresholds)
        passed_filters, _reasons = run_filters(text, cfg)
        if not passed_filters:
            results["reject_reasons"]["reject.filter"] += 1
            continue

        for threshold in THRESHOLDS:
            required = max(threshold, required_confidence_for_length(len(text)))
            if score >= required:
                wet_scores_by_threshold[threshold]["kept"] += 1
                wet_scores_by_threshold[threshold]["scores"].append(round(score, 4))

    # Aggregate per-WET stats
    top_labels = wet_labels.most_common(10)
    per_wet = {
        "url": wet_url,
        "docs_seen": wet_docs_seen,
        "top_10_labels": [{"lang": lang, "count": c} for lang, c in top_labels],
        "yields": {str(t): wet_scores_by_threshold[t]["kept"] for t in THRESHOLDS},
    }
    results["per_wet"].append(per_wet)

    log.info(
        "WET done: docs=%d, top_lang=%s, rw_yields=%s",
        wet_docs_seen,
        top_labels[:3],
        {str(t): wet_scores_by_threshold[t]["kept"] for t in THRESHOLDS},
    )


def main():
    parser = argparse.ArgumentParser(description="Gate G1: CC yield validation")
    parser.add_argument("--config", default="configs/default.yaml", help="Config file path")
    parser.add_argument("--max-wet-files", type=int, default=50, help="Number of WET files")
    args = parser.parse_args()

    cfg = load_config(args.config)
    setup_logging(cfg.logging.level)
    register_quality_filters()

    # Load WET URLs
    wet_path = Path(cfg.cc.wet_paths_file)
    if not wet_path.exists():
        log.error("WET paths file not found: %s", wet_path)
        sys.exit(1)

    with open(wet_path) as f:
        all_urls = [line.strip() for line in f if line.strip() and not line.startswith("#")]

    urls = all_urls[: args.max_wet_files]
    log.info("Processing %d WET files (of %d available)", len(urls), len(all_urls))

    results = {
        "start_time": time.time(),
        "config": {
            "wet_paths_file": cfg.cc.wet_paths_file,
            "max_wet_files": args.max_wet_files,
            "default_lid_threshold": cfg.lid.min_confidence,
            "test_thresholds": THRESHOLDS,
            "min_chars": cfg.filters.min_chars,
        },
        "total_docs_seen": 0,
        "global_labels": Counter(),
        "rw_scores": [],
        "reject_reasons": Counter(),
        "per_wet": [],
        "failed_wets": [],
    }

    for i, url in enumerate(urls, 1):
        log.info("--- WET %d/%d ---", i, len(urls))
        _process_wet(url, cfg, results)

    # Compute summary
    total_seen = results["total_docs_seen"]
    rw_scores = results["rw_scores"]
    total_rw_labeled = len(rw_scores)

    yields_by_threshold = {}
    for t in THRESHOLDS:
        kept = sum(w["yields"][str(t)] for w in results["per_wet"])
        rate = kept / total_seen if total_seen else 0
        yields_by_threshold[str(t)] = {
            "kept": kept,
            "keep_rate": round(rate, 8),
            "keep_pct": f"{rate * 100:.4f}%",
        }

    # Score distribution for rw-labeled docs
    score_dist = {}
    if rw_scores:
        sorted_scores = sorted(rw_scores)
        n = len(sorted_scores)
        score_dist = {
            "count": n,
            "min": sorted_scores[0],
            "p25": sorted_scores[n // 4],
            "median": sorted_scores[n // 2],
            "p75": sorted_scores[3 * n // 4],
            "max": sorted_scores[-1],
            "mean": round(sum(sorted_scores) / n, 4),
        }

    report = {
        "gate": "G1",
        "description": "CC yield validation — is low keep rate real scarcity or over-filtering?",
        "start_time": results["start_time"],
        "end_time": time.time(),
        "elapsed_s": round(time.time() - results["start_time"], 2),
        "wet_files_processed": len(results["per_wet"]),
        "wet_files_failed": len(results["failed_wets"]),
        "total_docs_seen": total_seen,
        "total_rw_labeled": total_rw_labeled,
        "rw_score_distribution": score_dist,
        "yields_by_threshold": yields_by_threshold,
        "global_top_20_labels": [
            {"lang": lang, "count": c} for lang, c in results["global_labels"].most_common(20)
        ],
        "reject_reasons": dict(results["reject_reasons"].most_common()),
        "per_wet_summary": results["per_wet"],
        "failed_wets": results["failed_wets"],
    }

    # Determine decision
    default_yield = yields_by_threshold.get(str(cfg.lid.min_confidence), {})
    low_yield = yields_by_threshold.get("0.65", {})
    if low_yield.get("kept", 0) > default_yield.get("kept", 0) * 3:
        report["decision"] = "THRESHOLD_TOO_STRICT"
        report["recommendation"] = (
            "Yield increased significantly at 0.65 threshold. "
            "Consider lowering lid.min_confidence. CC investment: HIGH."
        )
    elif total_rw_labeled < 50:
        report["decision"] = "REAL_SCARCITY"
        report["recommendation"] = (
            "Very few kin_Latn docs found regardless of threshold. "
            "CC investment: LOW. Focus on targeted crawling and external datasets."
        )
    else:
        report["decision"] = "MODERATE_SCARCITY"
        report["recommendation"] = (
            "Some kin_Latn docs found but yield is low. "
            "CC index mining (Phase 15) may help target .rw domains. CC investment: MEDIUM."
        )

    # Write report
    out_dir = Path("outputs/gate_checks")
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / "cc_yield_report.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)

    log.info("=" * 60)
    log.info("GATE G1 RESULTS")
    log.info("=" * 60)
    log.info("WET files processed: %d", len(results["per_wet"]))
    log.info("Total docs seen: %d", total_seen)
    log.info("Total kin_Latn labeled: %d", total_rw_labeled)
    if score_dist:
        log.info(
            "rw score distribution: median=%.4f, mean=%.4f",
            score_dist["median"],
            score_dist["mean"],
        )
    for t in THRESHOLDS:
        y = yields_by_threshold[str(t)]
        log.info("Threshold %.2f: kept=%d, rate=%s", t, y["kept"], y["keep_pct"])
    log.info("Decision: %s", report["decision"])
    log.info("Recommendation: %s", report["recommendation"])
    log.info("Report written to %s", report_path)


if __name__ == "__main__":
    main()

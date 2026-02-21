"""Aggregate multiple RunReport files into a dataset summary."""

import json
from collections import Counter
from pathlib import Path

from apps.common.logging import get_logger

log = get_logger(__name__)


def aggregate_reports(report_paths: list[Path]) -> dict:
    """Merge multiple RunReport JSONs into an aggregate summary."""
    total_docs_seen = 0
    total_docs_kept = 0
    total_docs_deduped = 0
    total_bytes = 0
    total_shards = 0
    total_tokens = 0
    total_kept_chars_sum = 0.0

    reject_reasons: Counter = Counter()
    domain_counts: Counter = Counter()
    lid_histogram: Counter = Counter()
    config_fingerprints: set = set()
    run_ids: list = []

    for path in report_paths:
        data = json.loads(path.read_text())
        run_ids.append(data.get("run_id", ""))

        total_docs_seen += data.get("docs_seen", 0)
        total_docs_kept += data.get("docs_kept", 0)
        total_docs_deduped += data.get("docs_deduped", 0)
        total_bytes += data.get("bytes_written", 0)
        total_shards += data.get("shards_written", 0)
        total_tokens += data.get("token_estimate_total", 0)
        total_kept_chars_sum += data.get("avg_doc_chars_kept", 0.0) * data.get("docs_kept", 0)

        for reason, count in data.get("reject_reasons", {}).items():
            reject_reasons[reason] += count

        for entry in data.get("top_domains_kept", []):
            domain_counts[entry["domain"]] += entry["docs"]

        for bucket, count in data.get("lid_score_histogram", {}).items():
            lid_histogram[bucket] += count

        fp = data.get("config_fingerprint", "")
        if fp:
            config_fingerprints.add(fp)

    if len(config_fingerprints) > 1:
        log.warning(
            "Multiple config fingerprints detected across %d runs: %s",
            len(report_paths),
            config_fingerprints,
        )

    keep_rate = total_docs_kept / total_docs_seen if total_docs_seen else 0.0
    avg_chars = total_kept_chars_sum / total_docs_kept if total_docs_kept else 0.0

    return {
        "runs": len(report_paths),
        "run_ids": run_ids,
        "total_docs_seen": total_docs_seen,
        "total_docs_kept": total_docs_kept,
        "total_docs_deduped": total_docs_deduped,
        "keep_rate": round(keep_rate, 4),
        "avg_doc_chars_kept": round(avg_chars, 1),
        "total_bytes_written": total_bytes,
        "total_shards": total_shards,
        "total_token_estimate": total_tokens,
        "reject_reasons": dict(reject_reasons.most_common()),
        "top_domains_kept": [{"domain": d, "docs": c} for d, c in domain_counts.most_common(30)],
        "lid_score_histogram": dict(sorted(lid_histogram.items())),
        "config_fingerprints": sorted(config_fingerprints),
        "config_consistent": len(config_fingerprints) <= 1,
    }

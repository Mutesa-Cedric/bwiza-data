"""Tests for multi-run report aggregator."""

import json

from apps.common.aggregate import aggregate_reports


def _write_report(tmp_path, run_id, docs_seen=100, docs_kept=50, **extra):
    data = {
        "run_id": run_id,
        "docs_seen": docs_seen,
        "docs_kept": docs_kept,
        "docs_deduped": extra.get("docs_deduped", 0),
        "bytes_written": extra.get("bytes_written", 1000),
        "shards_written": extra.get("shards_written", 1),
        "token_estimate_total": extra.get("token_estimate_total", 500),
        "avg_doc_chars_kept": extra.get("avg_doc_chars_kept", 200.0),
        "reject_reasons": extra.get("reject_reasons", {"reject.lid.not_rw": 30}),
        "top_domains_kept": extra.get("top_domains_kept", [{"domain": "ex.rw", "docs": 10}]),
        "lid_score_histogram": extra.get("lid_score_histogram", {"0.9-0.95": 20}),
        "config_fingerprint": extra.get("config_fingerprint", "aaa"),
    }
    path = tmp_path / f"{run_id}.json"
    path.write_text(json.dumps(data))
    return path


def test_aggregate_two_runs(tmp_path):
    p1 = _write_report(tmp_path, "run1")
    p2 = _write_report(tmp_path, "run2", docs_seen=200, docs_kept=100)

    result = aggregate_reports([p1, p2])
    assert result["runs"] == 2
    assert result["total_docs_seen"] == 300
    assert result["total_docs_kept"] == 150
    assert result["total_shards"] == 2
    assert result["config_consistent"] is True


def test_aggregate_warns_different_configs(tmp_path):
    p1 = _write_report(tmp_path, "run1", config_fingerprint="aaa")
    p2 = _write_report(tmp_path, "run2", config_fingerprint="bbb")

    result = aggregate_reports([p1, p2])
    assert result["config_consistent"] is False
    assert len(result["config_fingerprints"]) == 2


def test_aggregate_merges_reject_reasons(tmp_path):
    p1 = _write_report(tmp_path, "run1", reject_reasons={"reject.lid.not_rw": 10})
    p2 = _write_report(
        tmp_path, "run2", reject_reasons={"reject.lid.not_rw": 20, "reject.too_short": 5}
    )

    result = aggregate_reports([p1, p2])
    assert result["reject_reasons"]["reject.lid.not_rw"] == 30
    assert result["reject_reasons"]["reject.too_short"] == 5


def test_aggregate_merges_domains(tmp_path):
    p1 = _write_report(tmp_path, "run1", top_domains_kept=[{"domain": "a.rw", "docs": 5}])
    p2 = _write_report(tmp_path, "run2", top_domains_kept=[{"domain": "a.rw", "docs": 3}])

    result = aggregate_reports([p1, p2])
    assert result["top_domains_kept"][0] == {"domain": "a.rw", "docs": 8}


def test_aggregate_empty():
    result = aggregate_reports([])
    assert result["runs"] == 0
    assert result["total_docs_seen"] == 0

"""Tests for RunReport schema."""

import json

from apps.common.report_schema import RunReport


def test_default_report_has_all_keys():
    report = RunReport()
    d = report.to_dict()
    required = [
        "run_id",
        "source",
        "crawl_id",
        "started_at",
        "ended_at",
        "wet_files_attempted",
        "wet_files_succeeded",
        "docs_seen",
        "docs_kept",
        "docs_deduped",
        "bytes_written",
        "shards_written",
        "token_estimate_total",
        "avg_doc_chars_kept",
        "reject_reasons",
        "lid_score_histogram",
        "doc_length_histogram",
        "top_domains_kept",
        "config_fingerprint",
        "git_commit",
        "notes",
    ]
    for key in required:
        assert key in d, f"Missing key: {key}"


def test_json_roundtrip():
    report = RunReport(
        run_id="test_run",
        source="commoncrawl",
        docs_seen=100,
        docs_kept=50,
        reject_reasons={"reject.lid.not_rw": 30, "reject.too_short": 20},
    )
    text = report.to_json()
    restored = RunReport.from_json(text)
    assert restored.run_id == "test_run"
    assert restored.docs_seen == 100
    assert restored.reject_reasons == {"reject.lid.not_rw": 30, "reject.too_short": 20}


def test_to_json_is_valid_json():
    report = RunReport(run_id="r1", docs_kept=5)
    parsed = json.loads(report.to_json())
    assert parsed["run_id"] == "r1"


def test_from_dict_ignores_unknown_keys():
    data = {"run_id": "r1", "unknown_field": 42, "docs_kept": 10}
    report = RunReport.from_dict(data)
    assert report.run_id == "r1"
    assert report.docs_kept == 10


def test_deterministic_serialization():
    a = RunReport(run_id="r1", docs_seen=10).to_json()
    b = RunReport(run_id="r1", docs_seen=10).to_json()
    assert a == b

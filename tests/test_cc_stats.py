"""Tests for run stats."""

import json

from apps.cc_miner.stats import RunStats


def test_stats_to_dict():
    s = RunStats()
    s.docs_seen = 100
    s.docs_kept = 10
    s.duplicates = 5
    s.total_kept_chars = 4000
    s.wet_files_processed = 2
    s.reject_reasons["reject.lid.not_rw"] = 80
    s.reject_reasons["reject.too_short"] = 5

    d = s.to_dict()
    assert d["docs_seen"] == 100
    assert d["docs_kept"] == 10
    assert d["keep_ratio"] == 0.1
    assert d["token_estimate"] == 1000
    assert d["reject_reasons"]["reject.lid.not_rw"] == 80


def test_stats_write_json(tmp_path):
    s = RunStats()
    s.docs_seen = 50
    s.docs_kept = 5
    path = s.write_json(str(tmp_path), "test_run")
    assert path.exists()

    data = json.loads(path.read_text())
    assert data["docs_seen"] == 50


def test_empty_stats():
    s = RunStats()
    assert s.keep_ratio == 0.0
    assert s.avg_doc_length == 0.0
    assert s.token_estimate == 0

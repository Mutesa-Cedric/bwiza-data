"""Tests for RunReport builder."""

import json

from apps.cc_miner.report import ReportBuilder
from apps.common.config_types import AppConfig


def test_builder_produces_valid_report():
    builder = ReportBuilder(AppConfig(), "test_run")
    builder.record_wet_attempt()
    builder.record_wet_success()

    for _ in range(10):
        builder.record_doc_seen()
    for _ in range(5):
        builder.record_doc_kept(text_length=1000, lid_score=0.92, domain="example.rw")
    for _ in range(3):
        builder.record_reject("reject.lid.not_rw", lid_score=0.85)
    for _ in range(2):
        builder.record_reject("reject.too_short")

    builder.record_dedup()
    builder.record_shard_closed(shard_bytes=5000, token_estimate=1250)

    report = builder.build()
    assert report.run_id == "test_run"
    assert report.docs_seen == 10
    assert report.docs_kept == 5
    assert report.docs_deduped == 1
    assert report.shards_written == 1
    assert report.bytes_written == 5000
    assert report.avg_doc_chars_kept == 1000.0
    assert report.reject_reasons["reject.lid.not_rw"] == 3
    assert report.reject_reasons["reject.too_short"] == 2
    assert len(report.config_fingerprint) == 64
    assert report.top_domains_kept == [{"domain": "example.rw", "docs": 5}]


def test_builder_writes_to_disk(tmp_path):
    builder = ReportBuilder(AppConfig(), "test_run")
    builder.record_doc_seen()
    builder.record_doc_kept(500, 0.91)
    path = builder.write(str(tmp_path))
    assert path.exists()

    data = json.loads(path.read_text())
    assert data["run_id"] == "test_run"
    assert data["docs_kept"] == 1


def test_empty_report():
    builder = ReportBuilder(AppConfig(), "empty_run")
    report = builder.build()
    assert report.docs_seen == 0
    assert report.docs_kept == 0
    assert report.avg_doc_chars_kept == 0.0
    assert report.reject_reasons == {}


def test_lid_histogram_populated():
    builder = ReportBuilder(AppConfig(), "r1")
    builder.record_doc_kept(500, 0.92)
    builder.record_doc_kept(800, 0.87)
    builder.record_reject("reject.lid.not_rw", lid_score=0.60)

    report = builder.build()
    assert len(report.lid_score_histogram) > 0


def test_doc_length_histogram_populated():
    builder = ReportBuilder(AppConfig(), "r1")
    builder.record_doc_kept(300, 0.92)
    builder.record_doc_kept(1500, 0.93)

    report = builder.build()
    assert len(report.doc_length_histogram) > 0

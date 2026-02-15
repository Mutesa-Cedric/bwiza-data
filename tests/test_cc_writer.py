"""Tests for local JSONL writer."""

import json

from apps.cc_miner.writer import LocalWriter
from apps.common.config_types import AppConfig


def _cfg(tmp_path) -> AppConfig:
    cfg = AppConfig()
    cfg.output.local_dir = str(tmp_path)
    return cfg


def test_write_and_close(tmp_path):
    writer = LocalWriter(_cfg(tmp_path), "test_run")
    writer.write({"id": "1", "text": "hello"})
    writer.write({"id": "2", "text": "world"})
    writer.close()

    assert writer.count == 2
    assert writer.path.exists()

    lines = writer.path.read_text().strip().split("\n")
    assert len(lines) == 2
    assert json.loads(lines[0])["id"] == "1"


def test_empty_writer_no_file(tmp_path):
    writer = LocalWriter(_cfg(tmp_path), "empty_run")
    writer.close()

    assert writer.count == 0
    assert not writer.path.exists()

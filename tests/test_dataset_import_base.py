"""Tests for dataset import base module."""

from collections import Counter
from unittest.mock import MagicMock, patch

from apps.dataset_import.base import (
    DatasetImporter,
    ImportedDoc,
    ImportRunReport,
    import_and_process,
)


class _FakeImporter(DatasetImporter):
    """Test importer yielding canned docs."""

    def __init__(self, docs: list[ImportedDoc]):
        self._docs = docs

    @property
    def name(self) -> str:
        return "test_source"

    def load(self):
        yield from self._docs


def _make_doc(text: str, idx: int = 0) -> ImportedDoc:
    return ImportedDoc(
        text=text,
        source_dataset="test_dataset",
        source_id=str(idx),
        meta={"idx": idx},
    )


def test_imported_doc_defaults():
    doc = ImportedDoc(text="hello", source_dataset="ds")
    assert doc.source_id == ""
    assert doc.url == ""
    assert doc.meta == {}


def test_import_run_report_empty():
    report = ImportRunReport()
    d = report.to_dict()
    assert d["docs_seen"] == 0
    assert d["docs_kept"] == 0
    assert d["keep_rate"] == 0.0
    assert d["reject_reasons"] == {}


def test_import_run_report_with_data():
    report = ImportRunReport(
        docs_seen=100,
        docs_kept=75,
        total_kept_chars=50000,
        reject_reasons=Counter({"reject.too_short": 20, "reject.lid.not_rw": 5}),
    )
    d = report.to_dict()
    assert d["keep_rate"] == 0.75
    assert d["reject_reasons"]["reject.too_short"] == 20


@patch("apps.dataset_import.base.decide_keep")
def test_import_and_process_keeps_good_docs(mock_keep):
    """Good docs pass through the full pipeline."""
    from apps.cc_miner.keep import KeepDecision

    mock_keep.return_value = KeepDecision(
        keep=True, reason="keep", lang="kin_Latn", lid_score=0.95, normalized_text="good text"
    )

    dedup = MagicMock()
    dedup.is_duplicate.return_value = (False, "")

    writer = MagicMock()
    writer.write.return_value = None

    on_shard = MagicMock()
    cfg = MagicMock()

    importer = _FakeImporter([_make_doc("good text", 0), _make_doc("another good text", 1)])

    report = import_and_process(importer, cfg, dedup, writer, on_shard, run_id="test_run")

    assert report.docs_seen == 2
    assert report.docs_kept == 2
    assert report.total_kept_chars == len("good text") * 2
    assert writer.write.call_count == 2


@patch("apps.dataset_import.base.decide_keep")
def test_import_and_process_rejects_bad_docs(mock_keep):
    """Docs rejected by keep decision are counted in reject_reasons."""
    from apps.cc_miner.keep import KeepDecision

    mock_keep.return_value = KeepDecision(keep=False, reason="reject.too_short")

    dedup = MagicMock()
    writer = MagicMock()
    on_shard = MagicMock()
    cfg = MagicMock()

    importer = _FakeImporter([_make_doc("short", 0)])

    report = import_and_process(importer, cfg, dedup, writer, on_shard)

    assert report.docs_seen == 1
    assert report.docs_kept == 0
    assert report.reject_reasons["reject.too_short"] == 1
    writer.write.assert_not_called()


@patch("apps.dataset_import.base.decide_keep")
def test_import_and_process_dedup_rejects(mock_keep):
    """Docs caught by dedup are counted as rejected."""
    from apps.cc_miner.keep import KeepDecision

    mock_keep.return_value = KeepDecision(
        keep=True, reason="keep", lang="kin_Latn", lid_score=0.90, normalized_text="dup text"
    )

    dedup = MagicMock()
    dedup.is_duplicate.return_value = (True, "reject.dedup.exact")

    writer = MagicMock()
    on_shard = MagicMock()
    cfg = MagicMock()

    importer = _FakeImporter([_make_doc("dup text", 0)])

    report = import_and_process(importer, cfg, dedup, writer, on_shard)

    assert report.docs_seen == 1
    assert report.docs_kept == 0
    assert report.reject_reasons["reject.dedup.exact"] == 1
    writer.write.assert_not_called()


@patch("apps.dataset_import.base.decide_keep")
def test_import_and_process_calls_on_shard_closed(mock_keep):
    """When writer.write returns a ShardMeta, on_shard_closed is called."""
    from apps.cc_miner.keep import KeepDecision

    mock_keep.return_value = KeepDecision(
        keep=True, reason="keep", lang="kin_Latn", lid_score=0.95, normalized_text="text here"
    )

    dedup = MagicMock()
    dedup.is_duplicate.return_value = (False, "")

    shard_meta = MagicMock()
    writer = MagicMock()
    writer.write.return_value = shard_meta

    on_shard = MagicMock()
    cfg = MagicMock()

    importer = _FakeImporter([_make_doc("text here", 0)])

    import_and_process(importer, cfg, dedup, writer, on_shard)

    on_shard.assert_called_once_with(shard_meta)


def test_abstract_importer_cannot_instantiate():
    """DatasetImporter is abstract — can't be instantiated directly."""
    import pytest

    with pytest.raises(TypeError):
        DatasetImporter()  # type: ignore[abstract]

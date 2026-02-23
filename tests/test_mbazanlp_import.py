"""Tests for mbazaNLP Kinyarwanda importer."""

from unittest.mock import MagicMock, patch

from apps.dataset_import.mbazanlp import HF_DATASET_ID, MbazaNLPImporter


def _mock_dataset(rows):
    """Create a mock HF dataset from a list of dicts."""
    ds = MagicMock()
    ds.__len__ = MagicMock(return_value=len(rows))
    ds.__iter__ = MagicMock(return_value=iter(rows))
    return ds


@patch("datasets.load_dataset")
def test_load_yields_docs(mock_load):
    mock_load.return_value = _mock_dataset(
        [
            {"text": "Muraho neza"},
            {"text": "Amakuru yawe"},
        ]
    )

    importer = MbazaNLPImporter()
    docs = list(importer.load())

    assert len(docs) == 2
    assert docs[0].text == "Muraho neza"
    assert docs[0].source_dataset == HF_DATASET_ID
    assert docs[0].source_id == "0"
    assert docs[0].meta["license"] == "cc-by-4.0"
    assert docs[1].source_id == "1"

    mock_load.assert_called_once_with(HF_DATASET_ID, split="train")


@patch("datasets.load_dataset")
def test_skips_empty_text(mock_load):
    mock_load.return_value = _mock_dataset(
        [
            {"text": "Good text"},
            {"text": ""},
            {"text": None},
            {"text": "   "},
            {"text": "Also good"},
        ]
    )

    importer = MbazaNLPImporter()
    docs = list(importer.load())

    assert len(docs) == 2
    assert docs[0].text == "Good text"
    assert docs[1].text == "Also good"


@patch("datasets.load_dataset")
def test_source_ids_are_row_indices(mock_load):
    """Source IDs should be row indices, including skipped rows."""
    mock_load.return_value = _mock_dataset(
        [
            {"text": ""},
            {"text": "first real"},
            {"text": "second real"},
        ]
    )

    importer = MbazaNLPImporter()
    docs = list(importer.load())

    assert docs[0].source_id == "1"
    assert docs[1].source_id == "2"


def test_name():
    importer = MbazaNLPImporter()
    assert importer.name == "mbazanlp_v01.1"


@patch("datasets.load_dataset")
def test_meta_fields(mock_load):
    mock_load.return_value = _mock_dataset([{"text": "Hello"}])

    importer = MbazaNLPImporter()
    docs = list(importer.load())

    meta = docs[0].meta
    assert meta["dataset"] == HF_DATASET_ID
    assert meta["version"] == "01.1"
    assert meta["license"] == "cc-by-4.0"

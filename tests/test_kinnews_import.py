"""Tests for KinNews importer."""

from unittest.mock import MagicMock, patch

from apps.dataset_import.kinnews import (
    CATEGORY_LABELS,
    HF_CONFIG,
    HF_DATASET_ID,
    KinNewsImporter,
    label_to_category,
)


def _mock_split(rows):
    """Create a mock HF dataset split."""
    ds = MagicMock()
    ds.__len__ = MagicMock(return_value=len(rows))
    ds.__iter__ = MagicMock(return_value=iter(rows))
    return ds


def _mock_dataset(train_rows, test_rows=None):
    """Create a mock HF DatasetDict with train/test splits."""
    ds = MagicMock()
    splits = {"train": _mock_split(train_rows)}
    if test_rows is not None:
        splits["test"] = _mock_split(test_rows)
    ds.__contains__ = lambda self, key: key in splits
    ds.__getitem__ = lambda self, key: splits[key]
    return ds


@patch("datasets.load_dataset")
def test_load_yields_docs(mock_load):
    mock_load.return_value = _mock_dataset(
        [
            {"title": "Politiki", "content": "Amakuru ya politiki.", "label": 0},
            {"title": "Umukino", "content": "Inkuru y'umukino.", "label": 1},
        ]
    )

    importer = KinNewsImporter()
    docs = list(importer.load())

    assert len(docs) == 2
    assert docs[0].text == "Politiki\n\nAmakuru ya politiki."
    assert docs[0].source_dataset == HF_DATASET_ID
    assert docs[0].meta["category"] == "politics"
    assert docs[0].meta["label"] == 0
    assert docs[1].meta["category"] == "sport"

    mock_load.assert_called_once_with(HF_DATASET_ID, HF_CONFIG, trust_remote_code=True)


@patch("datasets.load_dataset")
def test_combines_train_and_test(mock_load):
    mock_load.return_value = _mock_dataset(
        train_rows=[{"title": "T1", "content": "Train doc.", "label": 0}],
        test_rows=[{"title": "T2", "content": "Test doc.", "label": 2}],
    )

    importer = KinNewsImporter()
    docs = list(importer.load())

    assert len(docs) == 2
    assert docs[0].meta["split"] == "train"
    assert docs[1].meta["split"] == "test"
    assert docs[1].meta["category"] == "economy"


@patch("datasets.load_dataset")
def test_skips_empty_content(mock_load):
    mock_load.return_value = _mock_dataset(
        [
            {"title": "Good", "content": "Has content.", "label": 0},
            {"title": "Empty", "content": "", "label": 1},
            {"title": "Blank", "content": "   ", "label": 2},
        ]
    )

    importer = KinNewsImporter()
    docs = list(importer.load())

    assert len(docs) == 1
    assert docs[0].text == "Good\n\nHas content."


@patch("datasets.load_dataset")
def test_empty_title_uses_content_only(mock_load):
    mock_load.return_value = _mock_dataset(
        [{"title": "", "content": "Just content here.", "label": 3}]
    )

    importer = KinNewsImporter()
    docs = list(importer.load())

    assert len(docs) == 1
    assert docs[0].text == "Just content here."


@patch("datasets.load_dataset")
def test_source_ids_sequential(mock_load):
    """Source IDs should be sequential across splits, including skipped rows."""
    mock_load.return_value = _mock_dataset(
        train_rows=[
            {"title": "A", "content": "", "label": 0},  # skipped (idx 0)
            {"title": "B", "content": "kept", "label": 1},  # idx 1
        ],
        test_rows=[
            {"title": "C", "content": "also kept", "label": 2},  # idx 2
        ],
    )

    importer = KinNewsImporter()
    docs = list(importer.load())

    assert docs[0].source_id == "1"
    assert docs[1].source_id == "2"


def test_label_to_category_valid():
    assert label_to_category(0) == "politics"
    assert label_to_category(13) == "relationship"
    assert label_to_category(5) == "history"


def test_label_to_category_out_of_range():
    assert label_to_category(14) == "unknown_14"
    assert label_to_category(-1) == "unknown_-1"


def test_category_labels_count():
    assert len(CATEGORY_LABELS) == 14


def test_name():
    importer = KinNewsImporter()
    assert importer.name == "kinnews"


@patch("datasets.load_dataset")
def test_meta_fields(mock_load):
    mock_load.return_value = _mock_dataset(
        [{"title": "Title", "content": "Content text.", "label": 7}]
    )

    importer = KinNewsImporter()
    docs = list(importer.load())

    meta = docs[0].meta
    assert meta["dataset"] == HF_DATASET_ID
    assert meta["config"] == HF_CONFIG
    assert meta["split"] == "train"
    assert meta["label"] == 7
    assert meta["category"] == "tourism"

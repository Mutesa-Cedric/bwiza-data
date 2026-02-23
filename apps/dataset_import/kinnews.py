"""KinNews Kinyarwanda news dataset importer."""

from __future__ import annotations

from typing import Iterator

from apps.common.logging import get_logger
from apps.dataset_import.base import DatasetImporter, ImportedDoc

log = get_logger(__name__)

HF_DATASET_ID = "kinnews_kirnews"
HF_CONFIG = "kinnews_cleaned"

# Label int (0-based) → English category name
CATEGORY_LABELS: list[str] = [
    "politics",
    "sport",
    "economy",
    "health",
    "entertainment",
    "history",
    "technology",
    "tourism",
    "culture",
    "fashion",
    "religion",
    "environment",
    "education",
    "relationship",
]


def label_to_category(label: int) -> str:
    """Convert a label int to its English category name."""
    if 0 <= label < len(CATEGORY_LABELS):
        return CATEGORY_LABELS[label]
    return f"unknown_{label}"


class KinNewsImporter(DatasetImporter):
    """Import kinnews_kirnews (kinnews_cleaned) from HuggingFace."""

    @property
    def name(self) -> str:
        return "kinnews"

    def load(self) -> Iterator[ImportedDoc]:
        from datasets import load_dataset

        log.info("Loading %s (%s) from HuggingFace...", HF_DATASET_ID, HF_CONFIG)
        ds = load_dataset(HF_DATASET_ID, HF_CONFIG, trust_remote_code=True)  # type: ignore[call-arg]

        doc_idx = 0
        for split_name in ("train", "test"):
            if split_name not in ds:
                log.warning("Split %r not found in %s", split_name, HF_DATASET_ID)
                continue

            split = ds[split_name]  # type: ignore[index]
            log.info("Processing split %s: %d rows", split_name, len(split))

            for row in split:
                title = str(row["title"]) if row["title"] else ""  # type: ignore[index]
                content = str(row["content"]) if row["content"] else ""  # type: ignore[index]
                label = int(row["label"])  # type: ignore[index]

                if not content or not content.strip():
                    doc_idx += 1
                    continue

                # Combine title + content for richer training text
                if title.strip():
                    text = title.strip() + "\n\n" + content.strip()
                else:
                    text = content.strip()

                category = label_to_category(label)

                yield ImportedDoc(
                    text=text,
                    source_dataset=HF_DATASET_ID,
                    source_id=str(doc_idx),
                    meta={
                        "dataset": HF_DATASET_ID,
                        "config": HF_CONFIG,
                        "split": split_name,
                        "label": label,
                        "category": category,
                    },
                )
                doc_idx += 1

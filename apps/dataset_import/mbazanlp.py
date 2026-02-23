"""mbazaNLP Kinyarwanda monolingual v01.1 importer."""

from __future__ import annotations

from typing import Iterator

from apps.common.logging import get_logger
from apps.dataset_import.base import DatasetImporter, ImportedDoc

log = get_logger(__name__)

HF_DATASET_ID = "mbazaNLP/kinyarwanda_monolingual_v01.1"


class MbazaNLPImporter(DatasetImporter):
    """Import mbazaNLP/kinyarwanda_monolingual_v01.1 from HuggingFace."""

    @property
    def name(self) -> str:
        return "mbazanlp_v01.1"

    def load(self) -> Iterator[ImportedDoc]:
        from datasets import load_dataset

        log.info("Loading %s from HuggingFace...", HF_DATASET_ID)
        ds = load_dataset(HF_DATASET_ID, split="train")
        log.info("Loaded %d rows from %s", len(ds), HF_DATASET_ID)

        for i, row in enumerate(ds):
            text = str(row["text"]) if row["text"] else ""  # type: ignore[index]
            if not text or not text.strip():
                continue

            yield ImportedDoc(
                text=text,
                source_dataset=HF_DATASET_ID,
                source_id=str(i),
                meta={
                    "dataset": HF_DATASET_ID,
                    "version": "01.1",
                    "license": "cc-by-4.0",
                },
            )

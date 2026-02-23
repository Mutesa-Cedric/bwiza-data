"""Base classes for external dataset importers."""

from __future__ import annotations

import abc
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Callable, Iterator

from apps.cc_miner.keep import decide_keep
from apps.common.config_types import AppConfig
from apps.common.hashing import hash_text
from apps.common.logging import get_logger
from apps.common.schema import Document

if TYPE_CHECKING:
    from apps.common.dedup_store import DedupStore
    from apps.common.shard_writer import ShardWriter

log = get_logger(__name__)


@dataclass
class ImportedDoc:
    """A raw document from an external dataset."""

    text: str
    source_dataset: str
    source_id: str = ""
    url: str = ""
    meta: dict = field(default_factory=dict)


class DatasetImporter(abc.ABC):
    """Abstract base for external dataset importers."""

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Short source name used in Document.source and manifests."""

    @abc.abstractmethod
    def load(self) -> Iterator[ImportedDoc]:
        """Yield raw documents from the external dataset."""


@dataclass
class ImportRunReport:
    """Stats from a dataset import run."""

    docs_seen: int = 0
    docs_kept: int = 0
    total_kept_chars: int = 0
    reject_reasons: Counter = field(default_factory=Counter)

    def to_dict(self) -> dict:
        return {
            "docs_seen": self.docs_seen,
            "docs_kept": self.docs_kept,
            "total_kept_chars": self.total_kept_chars,
            "keep_rate": (
                round(self.docs_kept / self.docs_seen, 4) if self.docs_seen > 0 else 0.0
            ),
            "reject_reasons": dict(self.reject_reasons),
        }


def import_and_process(
    importer: DatasetImporter,
    cfg: AppConfig,
    dedup: DedupStore,
    writer: ShardWriter,
    on_shard_closed: Callable,
    run_id: str = "",
) -> ImportRunReport:
    """Run an importer through the full quality pipeline.

    Steps per doc: normalize → min_chars → LID → filters → dedup → shard.
    """
    report = ImportRunReport()

    for raw_doc in importer.load():
        report.docs_seen += 1

        decision = decide_keep(raw_doc.text, cfg)
        if not decision.keep:
            report.reject_reasons[decision.reason] += 1
            continue

        text_hash = hash_text(decision.normalized_text)
        source = importer.name

        is_dup, reason = dedup.is_duplicate(
            text_hash, decision.normalized_text, text_hash, source, run_id
        )
        if is_dup:
            report.reject_reasons[reason] += 1
            continue

        doc = Document(
            id=text_hash,
            text=decision.normalized_text,
            source=source,
            url=raw_doc.url or None,
            crawl=raw_doc.source_dataset,
            fetched_at=datetime.now(timezone.utc).isoformat(),
            lang=decision.lang,
            lid_model="glotlid",
            lid_score=decision.lid_score,
            meta=raw_doc.meta,
        )

        result = writer.write(doc.to_json())
        if result is not None:
            on_shard_closed(result)

        report.docs_kept += 1
        report.total_kept_chars += len(doc.text)

        if report.docs_seen % 50000 == 0:
            log.info(
                "Progress: seen=%d kept=%d (%.1f%%)",
                report.docs_seen,
                report.docs_kept,
                100 * report.docs_kept / report.docs_seen,
            )

    return report

"""Wikipedia article processing pipeline: extract -> keep decision -> dedup -> Document."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Iterator

from apps.cc_miner.keep import KeepDecision, decide_keep
from apps.common.config_types import AppConfig
from apps.common.hashing import hash_text
from apps.common.logging import get_logger
from apps.common.schema import Document
from apps.wiki_miner.extract import WikiArticle

if TYPE_CHECKING:
    from apps.common.dedup_exact import ExactDedupStore
    from apps.common.dedup_store import DedupStore

log = get_logger(__name__)

WIKI_URL_TEMPLATE = "https://rw.wikipedia.org/wiki/{title}"


@dataclass
class WikiRunReport:
    """Stats from a Wikipedia processing run."""

    articles_seen: int = 0
    articles_kept: int = 0
    total_kept_chars: int = 0
    reject_reasons: Counter = field(default_factory=Counter)

    def to_dict(self) -> dict:
        return {
            "articles_seen": self.articles_seen,
            "articles_kept": self.articles_kept,
            "total_kept_chars": self.total_kept_chars,
            "keep_rate": (
                round(self.articles_kept / self.articles_seen, 4)
                if self.articles_seen > 0
                else 0.0
            ),
            "reject_reasons": dict(self.reject_reasons),
        }


def process_article(
    article: WikiArticle,
    cfg: AppConfig,
    dedup: DedupStore | ExactDedupStore,
) -> tuple[Document | None, KeepDecision]:
    """Run a single Wikipedia article through the quality pipeline.

    Returns (Document, decision) if kept, or (None, decision) if rejected.
    """
    decision = decide_keep(article.text, cfg)

    if not decision.keep:
        return None, decision

    text_hash = hash_text(decision.normalized_text)
    source = cfg.wiki.output_source

    is_dup, reason = dedup.is_duplicate(text_hash, decision.normalized_text, text_hash, source, "")
    if is_dup:
        return None, KeepDecision(
            keep=False,
            reason=reason,
            lang=decision.lang,
            lid_score=decision.lid_score,
        )

    wiki_url = WIKI_URL_TEMPLATE.format(title=article.title.replace(" ", "_"))

    doc = Document(
        id=text_hash,
        text=decision.normalized_text,
        source=source,
        url=wiki_url,
        crawl="wikipedia-dump",
        fetched_at=datetime.now(timezone.utc).isoformat(),
        lang=decision.lang,
        lid_model="glotlid",
        lid_score=decision.lid_score,
        meta={"title": article.title, "page_id": article.page_id},
    )

    return doc, decision


def process_articles(
    articles: Iterator[WikiArticle],
    cfg: AppConfig,
    dedup: DedupStore | ExactDedupStore,
) -> Iterator[tuple[Document, WikiRunReport]]:
    """Process Wikipedia articles through the quality pipeline.

    Yields (Document, report) for each kept article. The report is updated
    cumulatively — the final yielded report has the complete stats.
    """
    report = WikiRunReport()

    for article in articles:
        report.articles_seen += 1

        doc, decision = process_article(article, cfg, dedup)

        if doc is None:
            report.reject_reasons[decision.reason] += 1
            continue

        report.articles_kept += 1
        report.total_kept_chars += len(doc.text)
        yield doc, report

        if cfg.wiki.max_articles > 0 and report.articles_kept >= cfg.wiki.max_articles:
            log.info("Reached max_articles=%d", cfg.wiki.max_articles)
            break

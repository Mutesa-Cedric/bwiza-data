"""Canonical Document schema for kept documents."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Document:
    """A kept document ready for sharding."""

    id: str
    text: str
    source: str
    lang: str
    lid_model: str
    lid_score: float
    url: Optional[str] = None
    crawl: Optional[str] = None
    fetched_at: Optional[str] = None
    meta: dict = field(default_factory=dict)

    def to_json(self) -> dict:
        return {
            "id": self.id,
            "text": self.text,
            "source": self.source,
            "url": self.url,
            "crawl": self.crawl,
            "fetched_at": self.fetched_at,
            "lang": self.lang,
            "lid_model": self.lid_model,
            "lid_score": self.lid_score,
            "meta": self.meta,
        }

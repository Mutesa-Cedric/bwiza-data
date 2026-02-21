"""Schema for bilingual parallel pairs (rw ↔ en)."""

from dataclasses import dataclass, field

# Stable reject reason codes for parallel pairs
PARALLEL_REJECT_REASONS = {
    "reject.too_short",
    "reject.lid.low_confidence",
    "reject.lid.not_rw",
    "reject.lid.not_en",
    "reject.not_parallel",
    "reject.bad_alignment",
    "reject.duplicate",
    "reject.extraction_failed",
    "reject.fetch_failed",
}


@dataclass
class ParallelPair:
    """A bilingual rw↔en pair ready for sharding."""

    id: str
    rw_text: str
    en_text: str
    source: str
    url_rw: str = ""
    url_en: str = ""
    domain: str = ""
    fetched_at: str = ""
    rw_lid_score: float = 0.0
    en_lid_score: float = 0.0
    meta: dict = field(default_factory=dict)

    def to_json(self) -> dict:
        return {
            "id": self.id,
            "rw_text": self.rw_text,
            "en_text": self.en_text,
            "source": self.source,
            "url_rw": self.url_rw,
            "url_en": self.url_en,
            "domain": self.domain,
            "fetched_at": self.fetched_at,
            "rw_lid_score": self.rw_lid_score,
            "en_lid_score": self.en_lid_score,
            "meta": self.meta,
        }

    @classmethod
    def from_json(cls, data: dict) -> "ParallelPair":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

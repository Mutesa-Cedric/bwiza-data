"""Pair extraction pipeline: fetch both pages, extract, LID, validate."""

from dataclasses import dataclass
from datetime import datetime, timezone

from apps.common.config_types import ParallelConfig
from apps.common.hashing import hash_text
from apps.common.normalize import normalize_text
from apps.common.parallel_schema import ParallelPair
from apps.parallel_corpus.find_pairs import CandidatePair
from apps.targeted_crawler.extract import extract_main_text
from apps.targeted_crawler.fetch import FetchResult
from apps.targeted_crawler.seeds import canonical_domain

# GlotLID labels
_RW_LABELS = {"kin_Latn", "rw"}
_EN_LABELS = {"eng_Latn", "en"}


@dataclass
class PairResult:
    pair: ParallelPair | None
    reason: str


def process_candidate_pair(
    candidate: CandidatePair,
    rw_fetch: FetchResult,
    en_fetch: FetchResult,
    cfg: ParallelConfig,
    predict_lang_fn=None,
) -> PairResult:
    """Process a candidate bilingual pair through the full pipeline.

    Takes pre-fetched results for both URLs.
    predict_lang_fn should match the signature of apps.common.lid.predict_lang.
    """
    if predict_lang_fn is None:
        from apps.common.lid import predict_lang

        predict_lang_fn = predict_lang

    # Check fetch success
    if not rw_fetch.ok:
        return PairResult(pair=None, reason="reject.fetch_failed")
    if not en_fetch.ok:
        return PairResult(pair=None, reason="reject.fetch_failed")

    # Extract text
    rw_doc = extract_main_text(rw_fetch.content, url=candidate.url_rw)
    if rw_doc is None:
        return PairResult(pair=None, reason="reject.extraction_failed")

    en_doc = extract_main_text(en_fetch.content, url=candidate.url_en)
    if en_doc is None:
        return PairResult(pair=None, reason="reject.extraction_failed")

    # Normalize
    rw_text = normalize_text(rw_doc.text)
    en_text = normalize_text(en_doc.text)

    # Length check
    if len(rw_text) < cfg.min_chars:
        return PairResult(pair=None, reason="reject.too_short")
    if len(en_text) < cfg.min_chars:
        return PairResult(pair=None, reason="reject.too_short")

    # LID
    rw_lang, rw_score, _ = predict_lang_fn(rw_text)
    if rw_lang not in _RW_LABELS:
        return PairResult(pair=None, reason="reject.lid.not_rw")
    if rw_score < cfg.min_lid_conf:
        return PairResult(pair=None, reason="reject.lid.low_confidence")

    en_lang, en_score, _ = predict_lang_fn(en_text)
    if en_lang not in _EN_LABELS:
        return PairResult(pair=None, reason="reject.lid.not_en")
    if en_score < cfg.min_lid_conf:
        return PairResult(pair=None, reason="reject.lid.low_confidence")

    # Build pair
    from urllib.parse import urlparse

    parsed = urlparse(candidate.url_rw)
    domain = canonical_domain(parsed.hostname or "")

    pair_id = hash_text(rw_text + "||" + en_text)

    pair = ParallelPair(
        id=pair_id,
        rw_text=rw_text,
        en_text=en_text,
        source=cfg.output_source,
        url_rw=candidate.url_rw,
        url_en=candidate.url_en,
        domain=domain,
        fetched_at=datetime.now(timezone.utc).isoformat(),
        rw_lid_score=rw_score,
        en_lid_score=en_score,
        meta={"method": candidate.method, "confidence": candidate.confidence},
    )

    return PairResult(pair=pair, reason="keep")

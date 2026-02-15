"""Keep decision: determines whether a document should be retained."""

from dataclasses import dataclass

from apps.common.config_types import AppConfig
from apps.common.filters.base import run_filters
from apps.common.filters.purity import required_confidence_for_length
from apps.common.lid import predict_lang
from apps.common.normalize import normalize_text

# GlotLID labels for Kinyarwanda
_RW_LABELS = {"kin_Latn", "rw"}


@dataclass
class KeepDecision:
    keep: bool
    reason: str
    lang: str = ""
    lid_score: float = 0.0
    normalized_text: str = ""


def decide_keep(raw_text: str, cfg: AppConfig) -> KeepDecision:
    """Run full keep decision pipeline on a raw text."""
    text = normalize_text(raw_text)

    if len(text) < cfg.filters.min_chars:
        return KeepDecision(keep=False, reason="reject.too_short")

    lang, score, _model = predict_lang(text)

    if lang not in _RW_LABELS:
        return KeepDecision(keep=False, reason="reject.lid.not_rw",
                            lang=lang, lid_score=score)

    required = max(cfg.lid.min_confidence, required_confidence_for_length(len(text)))
    if score < required:
        return KeepDecision(keep=False, reason="reject.lid.low_confidence",
                            lang=lang, lid_score=score)

    passed, reasons = run_filters(text, cfg)
    if not passed:
        return KeepDecision(keep=False, reason=reasons[0],
                            lang=lang, lid_score=score)

    return KeepDecision(keep=True, reason="keep",
                        lang=lang, lid_score=score, normalized_text=text)

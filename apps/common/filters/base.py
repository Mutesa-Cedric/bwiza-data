"""Pluggable filter framework."""

from dataclasses import dataclass, field
from typing import Callable


@dataclass
class FilterResult:
    """Result of a single filter check."""

    passed: bool
    reason: str
    metrics: dict = field(default_factory=dict)


FilterFn = Callable[[str, object], FilterResult]

_REGISTRY: list[tuple[str, FilterFn]] = []


def register_filter(name: str, fn: FilterFn) -> None:
    """Register a filter function."""
    _REGISTRY.append((name, fn))


def run_filters(text: str, cfg: object) -> tuple[bool, list[str]]:
    """Run all registered filters. Returns (passed, list of failure reasons)."""
    reasons: list[str] = []
    for name, fn in _REGISTRY:
        result = fn(text, cfg)
        if not result.passed:
            reasons.append(result.reason)
    return (len(reasons) == 0, reasons)


def clear_registry() -> None:
    """Clear all registered filters (for testing)."""
    _REGISTRY.clear()


def get_registry() -> list[tuple[str, FilterFn]]:
    """Return current registry (for inspection)."""
    return list(_REGISTRY)

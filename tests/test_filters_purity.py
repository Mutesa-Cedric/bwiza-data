"""Tests for language purity helpers."""

from apps.common.filters.purity import required_confidence_for_length


def test_short_text_needs_high_confidence():
    assert required_confidence_for_length(100) == 0.95
    assert required_confidence_for_length(299) == 0.95


def test_medium_text():
    assert required_confidence_for_length(300) == 0.90
    assert required_confidence_for_length(499) == 0.90


def test_longer_text():
    assert required_confidence_for_length(500) == 0.85
    assert required_confidence_for_length(999) == 0.85


def test_long_text_baseline():
    assert required_confidence_for_length(1000) == 0.80
    assert required_confidence_for_length(10000) == 0.80

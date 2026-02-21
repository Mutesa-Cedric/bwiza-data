"""Tests for histogram utilities."""

from apps.common.histogram import LENGTH_BINS, LID_BINS, bucket, update_histogram


def test_bucket_below_first():
    assert bucket(0.5, LID_BINS) == "<0.8"


def test_bucket_in_range():
    assert bucket(0.82, LID_BINS) == "0.8-0.85"
    assert bucket(0.91, LID_BINS) == "0.9-0.95"


def test_bucket_at_boundary():
    assert bucket(0.85, LID_BINS) == "0.85-0.9"


def test_bucket_above_last():
    assert bucket(1.0, LID_BINS) == ">=1.0"


def test_bucket_length_bins():
    assert bucket(100, LENGTH_BINS) == "<200"
    assert bucket(300, LENGTH_BINS) == "200-500"
    assert bucket(15000, LENGTH_BINS) == ">=10000"


def test_update_histogram():
    hist = {}
    update_histogram(hist, 0.92, LID_BINS)
    update_histogram(hist, 0.93, LID_BINS)
    update_histogram(hist, 0.82, LID_BINS)
    assert hist == {"0.9-0.95": 2, "0.8-0.85": 1}


def test_deterministic_bucket_assignment():
    a = bucket(0.87, LID_BINS)
    b = bucket(0.87, LID_BINS)
    assert a == b

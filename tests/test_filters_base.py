"""Tests for filter framework."""

from apps.common.filters.base import (
    FilterResult,
    clear_registry,
    register_filter,
    run_filters,
)


class _FakeCfg:
    pass


def setup_function():
    clear_registry()


def test_no_filters_passes():
    passed, reasons = run_filters("text", _FakeCfg())
    assert passed is True
    assert reasons == []


def test_passing_filter():
    def always_pass(text, cfg):
        return FilterResult(passed=True, reason="keep")

    register_filter("pass", always_pass)
    passed, reasons = run_filters("text", _FakeCfg())
    assert passed is True
    assert reasons == []


def test_failing_filter():
    def always_fail(text, cfg):
        return FilterResult(passed=False, reason="reject.test")

    register_filter("fail", always_fail)
    passed, reasons = run_filters("text", _FakeCfg())
    assert passed is False
    assert "reject.test" in reasons


def test_multiple_filters_collect_reasons():
    def fail_a(text, cfg):
        return FilterResult(passed=False, reason="reject.a")

    def fail_b(text, cfg):
        return FilterResult(passed=False, reason="reject.b")

    register_filter("a", fail_a)
    register_filter("b", fail_b)
    passed, reasons = run_filters("text", _FakeCfg())
    assert passed is False
    assert len(reasons) == 2

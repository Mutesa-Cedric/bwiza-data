"""Tests for runtime and cost guardrails."""

import time

from apps.common.guardrails import GuardrailChecker, GuardrailConfig
from apps.common.run_state import RunState


def _state(**overrides: object) -> RunState:
    state = RunState(run_id="test", pipeline="cc_miner")
    for k, v in overrides.items():
        setattr(state, k, v)
    return state


def test_no_guardrails_pass():
    checker = GuardrailChecker(GuardrailConfig())
    triggered, reason = checker.check(_state(items_done=1000))
    assert triggered is False
    assert reason == ""


def test_max_items_triggers():
    checker = GuardrailChecker(GuardrailConfig(max_items=10))
    triggered, reason = checker.check(_state(items_done=10))
    assert triggered is True
    assert "max_items" in reason


def test_max_items_not_triggered():
    checker = GuardrailChecker(GuardrailConfig(max_items=10))
    triggered, reason = checker.check(_state(items_done=5))
    assert triggered is False


def test_max_bytes_triggers():
    checker = GuardrailChecker(GuardrailConfig(max_bytes_written=1000))
    triggered, reason = checker.check(_state(bytes_written=1000))
    assert triggered is True
    assert "max_bytes_written" in reason


def test_max_failed_items_triggers():
    checker = GuardrailChecker(GuardrailConfig(max_failed_items=3))
    triggered, reason = checker.check(_state(items_failed=3))
    assert triggered is True
    assert "max_failed_items" in reason


def test_max_runtime_triggers():
    checker = GuardrailChecker(GuardrailConfig(max_runtime_s=1))
    # Simulate elapsed time
    checker._start_time = time.monotonic() - 2
    triggered, reason = checker.check(_state())
    assert triggered is True
    assert "max_runtime_s" in reason


def test_max_runtime_not_triggered():
    checker = GuardrailChecker(GuardrailConfig(max_runtime_s=3600))
    triggered, reason = checker.check(_state())
    assert triggered is False


def test_multiple_guardrails_first_wins():
    checker = GuardrailChecker(GuardrailConfig(max_items=5, max_failed_items=2))
    triggered, reason = checker.check(_state(items_done=10, items_failed=1))
    assert triggered is True
    assert "max_items" in reason


def test_disabled_guardrails_zero():
    checker = GuardrailChecker(
        GuardrailConfig(
            max_items=0,
            max_runtime_s=0,
            max_bytes_written=0,
            max_failed_items=0,
        )
    )
    triggered, reason = checker.check(
        _state(items_done=999999, items_failed=999, bytes_written=999999)
    )
    assert triggered is False

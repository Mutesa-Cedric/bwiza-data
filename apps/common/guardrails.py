"""Runtime and cost guardrails for pipeline runs."""

import time
from dataclasses import dataclass

from apps.common.logging import get_logger
from apps.common.run_state import RunState

log = get_logger(__name__)


@dataclass
class GuardrailConfig:
    """Stop-condition thresholds. 0 means disabled."""

    max_items: int = 0
    max_runtime_s: int = 0
    max_bytes_written: int = 0
    max_failed_items: int = 0


class GuardrailChecker:
    """Check guardrails against current run state."""

    def __init__(self, config: GuardrailConfig) -> None:
        self._cfg = config
        self._start_time = time.monotonic()

    def check(self, state: RunState) -> tuple[bool, str]:
        """Check all guardrails. Returns (triggered, reason).

        If triggered is True, the run should stop gracefully.
        """
        if self._cfg.max_items > 0:
            if state.items_done >= self._cfg.max_items:
                reason = f"guardrail.max_items: {state.items_done} >= {self._cfg.max_items}"
                log.warning(reason)
                return True, reason

        if self._cfg.max_runtime_s > 0:
            elapsed = time.monotonic() - self._start_time
            if elapsed >= self._cfg.max_runtime_s:
                reason = f"guardrail.max_runtime_s: {elapsed:.0f}s >= {self._cfg.max_runtime_s}s"
                log.warning(reason)
                return True, reason

        if self._cfg.max_bytes_written > 0:
            if state.bytes_written >= self._cfg.max_bytes_written:
                reason = (
                    f"guardrail.max_bytes_written:"
                    f" {state.bytes_written}"
                    f" >= {self._cfg.max_bytes_written}"
                )
                log.warning(reason)
                return True, reason

        if self._cfg.max_failed_items > 0:
            if state.items_failed >= self._cfg.max_failed_items:
                reason = (
                    f"guardrail.max_failed_items:"
                    f" {state.items_failed}"
                    f" >= {self._cfg.max_failed_items}"
                )
                log.warning(reason)
                return True, reason

        return False, ""

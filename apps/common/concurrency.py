"""Bounded concurrency utilities for parallel task execution."""

import threading
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Callable

from apps.common.logging import get_logger

log = get_logger(__name__)


class BoundedWorkerPool:
    """Thread pool with a hard concurrency cap and synchronized callback.

    Results are delivered to callback synchronously (under lock) to
    prevent races on shared state like RunState or ShardWriter.
    """

    def __init__(self, max_workers: int, name: str = "pool") -> None:
        if max_workers < 1:
            raise ValueError(f"max_workers must be >= 1, got {max_workers}")
        self._max_workers = max_workers
        self._name = name
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix=name)
        self._lock = threading.Lock()
        self._futures: list[Future] = []
        self._errors: list[Exception] = []

    @property
    def max_workers(self) -> int:
        return self._max_workers

    @property
    def errors(self) -> list[Exception]:
        return list(self._errors)

    def submit(self, fn: Callable, *args, **kwargs) -> Future:
        """Submit a task. Returns the Future."""
        future = self._executor.submit(fn, *args, **kwargs)
        self._futures.append(future)
        return future

    def drain(self) -> list:
        """Wait for all submitted tasks and collect results.

        Returns list of results. Exceptions are collected in self.errors.
        """
        results = []
        for future in self._futures:
            try:
                results.append(future.result())
            except Exception as exc:
                with self._lock:
                    self._errors.append(exc)
                log.warning("[%s] Task failed: %s", self._name, exc)
        self._futures.clear()
        return results

    def shutdown(self, wait: bool = True) -> None:
        """Shutdown the pool."""
        self._executor.shutdown(wait=wait)

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.shutdown(wait=True)

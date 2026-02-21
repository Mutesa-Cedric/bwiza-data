"""Tests for bounded concurrency utilities."""

import threading
import time

import pytest

from apps.common.concurrency import BoundedWorkerPool


def test_basic_submit_and_drain():
    with BoundedWorkerPool(max_workers=2, name="test") as pool:
        pool.submit(lambda: 1)
        pool.submit(lambda: 2)
        results = pool.drain()
    assert sorted(results) == [1, 2]


def test_max_workers_enforced():
    active = {"count": 0, "peak": 0}
    lock = threading.Lock()

    def work():
        with lock:
            active["count"] += 1
            active["peak"] = max(active["peak"], active["count"])
        time.sleep(0.05)
        with lock:
            active["count"] -= 1
        return True

    with BoundedWorkerPool(max_workers=2, name="test") as pool:
        for _ in range(10):
            pool.submit(work)
        pool.drain()

    assert active["peak"] <= 2


def test_errors_collected():
    def failing():
        raise ValueError("boom")

    with BoundedWorkerPool(max_workers=2, name="test") as pool:
        pool.submit(failing)
        pool.submit(lambda: "ok")
        results = pool.drain()

    assert "ok" in results
    assert len(pool.errors) == 1
    assert "boom" in str(pool.errors[0])


def test_drain_clears_futures():
    with BoundedWorkerPool(max_workers=1, name="test") as pool:
        pool.submit(lambda: 1)
        results1 = pool.drain()
        assert results1 == [1]

        # Second drain should be empty
        results2 = pool.drain()
        assert results2 == []


def test_invalid_max_workers():
    with pytest.raises(ValueError, match="max_workers"):
        BoundedWorkerPool(max_workers=0)


def test_context_manager():
    pool = BoundedWorkerPool(max_workers=1, name="ctx")
    with pool:
        pool.submit(lambda: 42)
        results = pool.drain()
    assert results == [42]


def test_many_tasks():
    with BoundedWorkerPool(max_workers=4, name="test") as pool:
        for i in range(50):
            pool.submit(lambda x=i: x * 2)
        results = pool.drain()
    assert len(results) == 50
    assert sorted(results) == [i * 2 for i in range(50)]

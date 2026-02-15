"""Tests for exact dedup store."""

from apps.common.dedup_exact import ExactDedupStore


def test_new_item_returns_false():
    store = ExactDedupStore()
    assert store.check_and_add("abc") is False


def test_duplicate_returns_true():
    store = ExactDedupStore()
    store.check_and_add("abc")
    assert store.check_and_add("abc") is True


def test_different_items_not_duplicates():
    store = ExactDedupStore()
    store.check_and_add("abc")
    assert store.check_and_add("def") is False


def test_len():
    store = ExactDedupStore()
    assert len(store) == 0
    store.check_and_add("a")
    assert len(store) == 1
    store.check_and_add("a")  # duplicate
    assert len(store) == 1
    store.check_and_add("b")
    assert len(store) == 2

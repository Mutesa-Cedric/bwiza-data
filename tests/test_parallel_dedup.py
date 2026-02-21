"""Tests for parallel pair deduplication."""

from apps.parallel_corpus.dedup import PairDedupStore


def test_new_pair_accepted():
    store = PairDedupStore()
    is_dup, reason = store.check_and_add("rw text one", "en text one")
    assert not is_dup
    assert reason == "ok"


def test_exact_duplicate_rejected():
    store = PairDedupStore()
    store.check_and_add("rw text", "en text")
    is_dup, reason = store.check_and_add("rw text", "en text")
    assert is_dup
    assert reason == "reject.duplicate"


def test_different_pairs_accepted():
    store = PairDedupStore()
    store.check_and_add("rw one", "en one")
    is_dup, reason = store.check_and_add("rw two", "en two")
    assert not is_dup


def test_side_spam_rejected():
    store = PairDedupStore(max_side_repeats=2)
    store.check_and_add("same rw", "en one")
    store.check_and_add("same rw", "en two")
    is_dup, reason = store.check_and_add("same rw", "en three")
    assert is_dup
    assert reason == "reject.duplicate"


def test_en_side_spam_rejected():
    store = PairDedupStore(max_side_repeats=2)
    store.check_and_add("rw one", "same en")
    store.check_and_add("rw two", "same en")
    is_dup, reason = store.check_and_add("rw three", "same en")
    assert is_dup


def test_len():
    store = PairDedupStore()
    assert len(store) == 0
    store.check_and_add("a", "b")
    assert len(store) == 1
    store.check_and_add("a", "b")  # duplicate, but still in seen
    assert len(store) == 1
    store.check_and_add("c", "d")
    assert len(store) == 2

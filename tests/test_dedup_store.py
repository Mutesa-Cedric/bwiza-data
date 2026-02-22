"""Tests for persistent cross-run dedup store."""

from apps.common.dedup_store import DedupStore


def test_exact_dedup_persists(tmp_path):
    db = tmp_path / "dedup.db"

    # Session 1: add a hash
    with DedupStore(db, enable_fuzzy=False) as store:
        assert not store.check_and_add_exact("abc123", "cc", "run1")
        assert store.has_exact("abc123")

    # Session 2: same hash detected as duplicate
    with DedupStore(db, enable_fuzzy=False) as store:
        assert store.has_exact("abc123")
        assert store.check_and_add_exact("abc123", "cc", "run2")


def test_exact_different_hashes(tmp_path):
    with DedupStore(tmp_path / "dedup.db", enable_fuzzy=False) as store:
        assert not store.check_and_add_exact("hash_a", "cc", "run1")
        assert not store.check_and_add_exact("hash_b", "targeted", "run1")
        assert store.check_and_add_exact("hash_a", "cc", "run2")


def test_cross_source_exact_dedup(tmp_path):
    """Same document from two different sources is detected."""
    with DedupStore(tmp_path / "dedup.db", enable_fuzzy=False) as store:
        assert not store.check_and_add_exact("same_hash", "commoncrawl", "run1")
        assert store.check_and_add_exact("same_hash", "targeted_web", "run2")


def test_fuzzy_dedup(tmp_path):
    with DedupStore(tmp_path / "dedup.db", fuzzy_threshold=0.8) as store:
        text = "Muraho neza amakuru yawe ni ryari twongera kubonana " * 10
        assert not store.check_and_add_fuzzy(text, "doc1", "cc", "run1")
        # Exact same text again
        assert store.check_and_add_fuzzy(text, "doc2", "cc", "run1")


def test_combined_is_duplicate(tmp_path):
    with DedupStore(tmp_path / "dedup.db", enable_fuzzy=False) as store:
        dup, reason = store.is_duplicate("h1", "text1", "d1", "cc", "r1")
        assert not dup
        assert reason == ""

        dup, reason = store.is_duplicate("h1", "text1", "d2", "cc", "r1")
        assert dup
        assert reason == "reject.dedup.exact"


def test_stats(tmp_path):
    with DedupStore(tmp_path / "dedup.db", enable_fuzzy=False) as store:
        store.check_and_add_exact("h1", "cc", "run1")
        store.check_and_add_exact("h2", "targeted", "run1")
        store.check_and_add_exact("h1", "cc", "run2")  # dup

        s = store.stats()
        assert s["exact_total"] == 2
        assert s["exact_hits_this_session"] == 1
        assert s["exact_by_source"]["cc"] == 1
        assert s["exact_by_source"]["targeted"] == 1


def test_fuzzy_disabled(tmp_path):
    with DedupStore(tmp_path / "dedup.db", enable_fuzzy=False) as store:
        # Fuzzy check should always return False when disabled
        assert not store.check_and_add_fuzzy("any text", "d1", "cc", "r1")


def test_context_manager(tmp_path):
    db = tmp_path / "dedup.db"
    with DedupStore(db, enable_fuzzy=False) as store:
        store.add_exact("h1", "cc", "run1")
    # File should exist after close
    assert db.exists()


def test_parent_dirs_created(tmp_path):
    db = tmp_path / "nested" / "deep" / "dedup.db"
    with DedupStore(db, enable_fuzzy=False) as store:
        store.add_exact("h1", "cc", "run1")
    assert db.exists()

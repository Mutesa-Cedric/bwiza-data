"""Tests for MinHash fuzzy deduplication."""

import random

from apps.common.dedup_minhash import MinHashDedup, _word_shingles


def test_word_shingles_basic():
    text = "one two three four five six"
    shingles = _word_shingles(text, k=5)
    assert len(shingles) == 2
    assert shingles[0] == "one two three four five"
    assert shingles[1] == "two three four five six"


def test_word_shingles_short_text():
    shingles = _word_shingles("hello world", k=5)
    assert shingles == ["hello world"]


def test_word_shingles_empty():
    assert _word_shingles("", k=5) == []


def test_exact_duplicate_detected():
    dedup = MinHashDedup(threshold=0.8)
    text = "Muraho neza! Amakuru yawe? " * 20
    assert not dedup.check_and_add(text)
    assert dedup.check_and_add(text)


def test_near_duplicate_detected():
    """Near-duplicate with prefix/suffix added should be detected."""
    dedup = MinHashDedup(threshold=0.7)
    # Real-ish article text — long enough for many shingles
    base = (
        "Igihugu cy'u Rwanda kiherereye mu burasirazuba bw'Afurika. "
        "Umujyi mukuru ni Kigali. Abantu barenga miliyoni cumi na ebyiri "
        "batuye mu gihugu. Ururimi rw'ikinyarwanda ni ururimi rusange. "
        "Ubuhinzi ni umwuga ukomeye cyane mu bukungu bw'igihugu. "
        "Ikawa n'icyayi ni ibicuruzwa by'ingenzi byoherezwa mu mahanga. "
        "Rwanda ikunda umuganda buri kwezi. Abaturage bose bagomba gukora."
    )
    assert not dedup.check_and_add(base)

    # Add boilerplate prefix/suffix (common near-dup pattern)
    modified = "Soma inkuru hano: " + base + " Ubu butumwa bwanditswe na AI Bwiza."
    assert dedup.check_and_add(modified)


def test_different_documents_not_flagged():
    dedup = MinHashDedup(threshold=0.8)
    text_a = "Umuganda ni umuhango ukomeye mu Rwanda. Buri kwezi abantu bakora umuganda."
    text_a = text_a * 5
    text_b = "Ikipe y'umupira w'amaguru y'u Rwanda yatsinze umukino wayo wa nyuma."
    text_b = text_b * 5
    assert not dedup.check_and_add(text_a)
    assert not dedup.check_and_add(text_b)


def test_empty_text_handling():
    dedup = MinHashDedup(threshold=0.8)
    assert not dedup.check_and_add("")
    assert dedup.check_and_add("")


def test_threshold_sensitivity_strict():
    """Strict threshold (0.95) should only catch near-identical docs."""
    dedup = MinHashDedup(threshold=0.95)
    words = "abana beza bahiga inkoko mu murima wacu mukuru cyane" * 10
    word_list = words.split()
    assert not dedup.check_and_add(words)

    # 20% edit — should NOT be flagged at 0.95 threshold
    modified = list(word_list)
    rng = random.Random(42)
    n_changes = max(1, len(modified) // 5)
    for idx in rng.sample(range(len(modified)), n_changes):
        modified[idx] = "igitabo"
    assert not dedup.check_and_add(" ".join(modified))


def test_threshold_sensitivity_loose():
    """Loose threshold (0.5) catches truncated version of same text."""
    dedup = MinHashDedup(threshold=0.5)
    base = (
        "Igihugu cy'u Rwanda kiherereye mu burasirazuba bw'Afurika. "
        "Umujyi mukuru ni Kigali. Abantu barenga miliyoni cumi na ebyiri "
        "batuye mu gihugu. Ururimi rw'ikinyarwanda ni ururimi rusange. "
        "Ubuhinzi ni umwuga ukomeye cyane mu bukungu bw'igihugu. "
        "Ikawa n'icyayi ni ibicuruzwa by'ingenzi byoherezwa mu mahanga. "
        "Rwanda ikunda umuganda buri kwezi. Abaturage bose bagomba gukora. "
        "Umuganda ni umuhango ukomeye cyane mu mibereho y'abanyarwanda. "
        "Buri wa mbere mu kwezi abaturage bose bakora imirimo yo kubaka igihugu."
    )
    assert not dedup.check_and_add(base)

    # Keep first ~60% of the text — should still match at 0.5
    words = base.split()
    truncated = " ".join(words[: len(words) * 3 // 5])
    assert dedup.check_and_add(truncated)


def test_stats():
    dedup = MinHashDedup(threshold=0.8)
    text = "Muraho neza amakuru yawe ni ryari twongera kubonana " * 10
    dedup.check_and_add(text)
    dedup.check_and_add(text)  # duplicate
    dedup.check_and_add("completely different text " * 10)

    s = dedup.stats()
    assert s["total_indexed"] == 2
    assert s["duplicates_found"] == 1
    assert s["total_checked"] == 3


def test_is_duplicate_does_not_add():
    dedup = MinHashDedup(threshold=0.8)
    text = "Muraho neza amakuru yawe " * 10
    assert not dedup.is_duplicate(text)
    assert not dedup.is_duplicate(text)  # still not added
    dedup.add(text)
    assert dedup.is_duplicate(text)


def test_add_then_check():
    dedup = MinHashDedup(threshold=0.8)
    text = "Igihugu cyacu kiracyiza " * 10
    dedup.add(text)
    assert dedup.is_duplicate(text)

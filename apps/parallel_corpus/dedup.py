"""Pair-level deduplication for parallel corpus."""

from apps.common.hashing import hash_text
from apps.common.normalize import normalize_text


class PairDedupStore:
    """Deduplicate parallel pairs using stable hashing.

    Tracks:
    - Exact pair dedup: hash(normalize(rw) + "||" + normalize(en))
    - Per-side dedup: tracks how many times each side appears
    """

    def __init__(self, max_side_repeats: int = 5):
        self._seen_pairs: set[str] = set()
        self._rw_counts: dict[str, int] = {}
        self._en_counts: dict[str, int] = {}
        self._max_side_repeats = max_side_repeats

    def check_and_add(self, rw_text: str, en_text: str) -> tuple[bool, str]:
        """Check if a pair is duplicate. Returns (is_dup, reason).

        Returns (False, "ok") if the pair is new and accepted.
        """
        rw_norm = normalize_text(rw_text)
        en_norm = normalize_text(en_text)

        pair_hash = hash_text(rw_norm + "||" + en_norm)
        if pair_hash in self._seen_pairs:
            return True, "reject.duplicate"
        self._seen_pairs.add(pair_hash)

        # Check per-side spam
        rw_hash = hash_text(rw_norm)
        en_hash = hash_text(en_norm)

        rw_count = self._rw_counts.get(rw_hash, 0)
        if rw_count >= self._max_side_repeats:
            return True, "reject.duplicate"

        en_count = self._en_counts.get(en_hash, 0)
        if en_count >= self._max_side_repeats:
            return True, "reject.duplicate"

        self._rw_counts[rw_hash] = rw_count + 1
        self._en_counts[en_hash] = en_count + 1

        return False, "ok"

    def __len__(self) -> int:
        return len(self._seen_pairs)

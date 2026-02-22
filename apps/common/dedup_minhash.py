"""MinHash LSH fuzzy deduplication for near-duplicate detection."""

from datasketch import MinHash, MinHashLSH


def _word_shingles(text: str, k: int = 5) -> list[str]:
    """Generate word-level k-shingles from text."""
    words = text.lower().split()
    if len(words) < k:
        return [" ".join(words)] if words else []
    return [" ".join(words[i : i + k]) for i in range(len(words) - k + 1)]


def _compute_minhash(text: str, num_perm: int = 128) -> MinHash:
    """Compute MinHash signature from word 5-grams."""
    m = MinHash(num_perm=num_perm)
    for shingle in _word_shingles(text):
        m.update(shingle.encode("utf-8"))
    return m


class MinHashDedup:
    """Fuzzy deduplication using MinHash LSH."""

    def __init__(self, threshold: float = 0.8, num_perm: int = 128) -> None:
        self.threshold = threshold
        self.num_perm = num_perm
        self._lsh = MinHashLSH(threshold=threshold, num_perm=num_perm)
        self._count = 0
        self._duplicates = 0

    def is_duplicate(self, text: str) -> bool:
        """Check if text is a near-duplicate of any previously added text."""
        mh = _compute_minhash(text, self.num_perm)
        return len(self._lsh.query(mh)) > 0

    def add(self, text: str) -> None:
        """Add text to the index."""
        mh = _compute_minhash(text, self.num_perm)
        key = f"doc_{self._count}"
        self._count += 1
        self._lsh.insert(key, mh)

    def check_and_add(self, text: str) -> bool:
        """Check if duplicate, then add. Returns True if duplicate."""
        mh = _compute_minhash(text, self.num_perm)
        if len(self._lsh.query(mh)) > 0:
            self._duplicates += 1
            return True
        key = f"doc_{self._count}"
        self._count += 1
        self._lsh.insert(key, mh)
        return False

    def stats(self) -> dict:
        """Return dedup statistics."""
        return {
            "total_checked": self._count + self._duplicates,
            "total_indexed": self._count,
            "duplicates_found": self._duplicates,
        }

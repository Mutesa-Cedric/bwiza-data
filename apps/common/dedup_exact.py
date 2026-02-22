"""In-memory exact deduplication store."""


class ExactDedupStore:
    """Set-based exact dedup. Storage backend is swappable later."""

    def __init__(self) -> None:
        self._seen: set[str] = set()

    def check_and_add(self, hash_value: str) -> bool:
        """Return True if duplicate (already seen), False if new."""
        if hash_value in self._seen:
            return True
        self._seen.add(hash_value)
        return False

    def is_duplicate(
        self,
        sha256: str,
        text: str,
        doc_id: str,
        source: str,
        run_id: str,
    ) -> tuple[bool, str]:
        """Combined check matching DedupStore interface. Exact only."""
        if self.check_and_add(sha256):
            return True, "reject.dedup.exact"
        return False, ""

    def close(self) -> None:
        """No-op for in-memory store."""

    def __len__(self) -> int:
        return len(self._seen)

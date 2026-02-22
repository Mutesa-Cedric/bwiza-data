"""Factory for creating the appropriate dedup backend based on config."""

from apps.common.config_types import DedupConfig
from apps.common.dedup_exact import ExactDedupStore
from apps.common.dedup_store import DedupStore
from apps.common.logging import get_logger

log = get_logger(__name__)


def create_dedup(cfg: DedupConfig) -> DedupStore | ExactDedupStore:
    """Create a dedup store based on config.

    If store_path is set, returns a persistent DedupStore (SQLite + optional fuzzy).
    Otherwise returns an in-memory ExactDedupStore (backward-compatible fallback).
    """
    if cfg.store_path:
        log.info("Using persistent DedupStore at %s", cfg.store_path)
        return DedupStore(
            db_path=cfg.store_path,
            fuzzy_threshold=cfg.fuzzy_threshold,
            fuzzy_num_perm=cfg.fuzzy_num_perm,
            enable_fuzzy=cfg.enable_fuzzy,
        )
    log.info("No dedup store_path configured, using in-memory ExactDedupStore")
    return ExactDedupStore()

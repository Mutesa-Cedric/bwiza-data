#!/usr/bin/env python3
"""Smoke test: loads config, sets up logging, verifies basic imports."""

import sys


def main() -> int:
    from apps.common.config import load_config
    from apps.common.logging import get_logger, setup_logging

    cfg = load_config()
    setup_logging(cfg.logging.level)
    log = get_logger("smoke_test")

    log.info("Config loaded: lid.min_confidence=%s", cfg.lid.min_confidence)
    log.info("Config loaded: filters.min_chars=%s", cfg.filters.min_chars)
    log.info("Config loaded: sharding.target_compressed_mb=%s", cfg.sharding.target_compressed_mb)
    log.info("Smoke test passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Tests for centralized logging."""

import logging

from apps.common.logging import get_logger, setup_logging


def test_setup_logging_sets_level():
    setup_logging("DEBUG")
    assert logging.getLogger().level == logging.DEBUG
    setup_logging("INFO")
    assert logging.getLogger().level == logging.INFO


def test_get_logger_returns_named():
    logger = get_logger("test.module")
    assert logger.name == "test.module"
    assert isinstance(logger, logging.Logger)

"""Tests for logging_config module."""

import json
import logging

from linkedin_sync.logging_config import configure_logging, get_logger


class TestConfigureLogging:
    def test_human_readable_mode(self, capsys):
        configure_logging(json_logs=False, verbosity=logging.DEBUG)
        logger = get_logger("test.human")
        logger.info("test_message", key="value")
        captured = capsys.readouterr()
        assert "test_message" in captured.err
        assert "key" in captured.err

    def test_json_mode(self, capsys):
        configure_logging(json_logs=True, verbosity=logging.DEBUG)
        logger = get_logger("test.json")
        logger.info("json_event", number=42)
        captured = capsys.readouterr()
        # Each line should be valid JSON
        for line in captured.err.strip().split("\n"):
            if line:
                data = json.loads(line)
                assert data["event"] == "json_event"
                assert data["number"] == 42

    def test_respects_verbosity(self, capsys):
        configure_logging(json_logs=True, verbosity=logging.WARNING)
        logger = get_logger("test.verbosity")
        logger.info("should_not_appear")
        logger.warning("should_appear")
        captured = capsys.readouterr()
        assert "should_not_appear" not in captured.err
        assert "should_appear" in captured.err

    def test_get_logger_returns_structlog_logger(self):
        configure_logging(json_logs=False)
        logger = get_logger("test.bound")
        # structlog.get_logger returns a BoundLoggerLazyProxy before first use
        assert hasattr(logger, "info")
        assert hasattr(logger, "warning")
        assert hasattr(logger, "error")
        assert hasattr(logger, "debug")

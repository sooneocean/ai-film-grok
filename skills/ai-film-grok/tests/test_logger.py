"""Tests for logger.py — unified structured logging.

Previously had ZERO test coverage. Tests cover:
  - LogLevel enum and resolution
  - Logger level filtering (DEBUG/INFO/WARN/ERROR)
  - JSON vs human format
  - Counters
  - Module-level API (log, get_logger, set_level)
"""

from __future__ import annotations

import io
import json
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from logger import (  # noqa: E402
    Logger,
    LogLevel,
    get_logger,
    log,
    set_level,
)


class TestLogLevel(unittest.TestCase):
    """LogLevel enum values."""

    def test_ordering(self):
        self.assertLess(LogLevel.DEBUG.value, LogLevel.INFO.value)
        self.assertLess(LogLevel.INFO.value, LogLevel.WARN.value)
        self.assertLess(LogLevel.WARN.value, LogLevel.ERROR.value)

    def test_names(self):
        self.assertEqual(LogLevel.DEBUG.name, "DEBUG")
        self.assertEqual(LogLevel.ERROR.name, "ERROR")


class TestLoggerLevelFiltering(unittest.TestCase):
    """Logger respects level threshold."""

    def test_debug_filtered_at_info(self):
        """DEBUG messages are suppressed when level=INFO."""
        logger = Logger(name="test", level=LogLevel.INFO)
        buf = io.StringIO()
        # Redirect stderr temporarily
        old = sys.stderr
        sys.stderr = buf
        try:
            logger.debug("should not appear")
            logger.info("should appear")
        finally:
            sys.stderr = old
        self.assertNotIn("should not appear", buf.getvalue())
        self.assertIn("should appear", buf.getvalue())

    def test_error_at_debug_level(self):
        """All levels pass at DEBUG."""
        logger = Logger(name="test", level=LogLevel.DEBUG)
        buf = io.StringIO()
        old = sys.stderr
        sys.stderr = buf
        try:
            logger.debug("dbg")
            logger.info("inf")
            logger.warn("wrn")
            logger.error("err")
        finally:
            sys.stderr = old
        output = buf.getvalue()
        self.assertIn("dbg", output)
        self.assertIn("err", output)

    def test_set_level(self):
        """set_level changes filtering dynamically."""
        logger = Logger(name="test", level=LogLevel.ERROR)
        buf = io.StringIO()
        old = sys.stderr
        sys.stderr = buf
        try:
            logger.info("before")
            logger.set_level(LogLevel.DEBUG)
            logger.info("after")
        finally:
            sys.stderr = old
        self.assertNotIn("before", buf.getvalue())
        self.assertIn("after", buf.getvalue())


class TestLoggerFormat(unittest.TestCase):
    """Logger outputs JSON or human format."""

    def test_json_format_default(self):
        """Default output is JSON with timestamp/level/module/message."""
        logger = Logger(name="testmod", level=LogLevel.INFO)
        buf = io.StringIO()
        old = sys.stderr
        sys.stderr = buf
        try:
            logger.info("hello")
        finally:
            sys.stderr = old
        line = buf.getvalue().strip()
        data = json.loads(line)
        self.assertEqual(data["level"], "INFO")
        self.assertEqual(data["message"], "hello")
        self.assertEqual(data["module"], "testmod")
        self.assertIn("timestamp", data)

    def test_human_format(self):
        """Human format: [LEVEL] [module] message."""
        import os

        old_env = os.environ.get("AIFILM_LOG_FORMAT", "")
        os.environ["AIFILM_LOG_FORMAT"] = "human"
        try:
            logger = Logger(name="testmod", level=LogLevel.INFO)
            buf = io.StringIO()
            old = sys.stderr
            sys.stderr = buf
            try:
                logger.info("hello")
            finally:
                sys.stderr = old
            line = buf.getvalue().strip()
            self.assertTrue(line.startswith("[INFO]"))
            self.assertIn("hello", line)
        finally:
            if old_env:
                os.environ["AIFILM_LOG_FORMAT"] = old_env
            else:
                os.environ.pop("AIFILM_LOG_FORMAT", None)

    def test_extra_field_in_json(self):
        """Extra dict is included in JSON output."""
        logger = Logger(name="test", level=LogLevel.INFO)
        buf = io.StringIO()
        old = sys.stderr
        sys.stderr = buf
        try:
            logger.info("msg", extra={"key": "value"})
        finally:
            sys.stderr = old
        data = json.loads(buf.getvalue().strip())
        self.assertEqual(data["extra"]["key"], "value")


class TestLoggerCounters(unittest.TestCase):
    """Logger counters for metrics."""

    def test_count_increments(self):
        logger = Logger(name="test")
        logger.count("api_calls")
        logger.count("api_calls")
        self.assertEqual(logger.counts()["api_calls"], 2)

    def test_count_delta(self):
        logger = Logger(name="test")
        logger.count("tokens", delta=100)
        logger.count("tokens", delta=50)
        self.assertEqual(logger.counts()["tokens"], 150)

    def test_counts_returns_copy(self):
        logger = Logger(name="test")
        logger.count("x")
        c = logger.counts()
        c["x"] = 999
        self.assertEqual(logger.counts()["x"], 1)


class TestModuleLevelAPI(unittest.TestCase):
    """Module-level log/set_level/get_logger functions."""

    def test_log_function_is_plain_stderr(self):
        """log() stays a plain one-line stderr shim (not JSON)."""
        buf = io.StringIO()
        old = sys.stderr
        sys.stderr = buf
        try:
            log("test message")
        finally:
            sys.stderr = old
        out = buf.getvalue()
        self.assertIn("test message", out)
        self.assertFalse(out.strip().startswith("{"))

    def test_get_logger_named(self):
        """get_logger returns a Logger with the given name."""
        logger = get_logger("mymodule")
        self.assertEqual(logger._name, "mymodule")

    def test_set_level_affects_default_structured_logger(self):
        """set_level changes the default structured Logger, not plain log()."""
        from logger import _DEFAULT

        old_level = _DEFAULT._level
        set_level(LogLevel.ERROR)
        buf = io.StringIO()
        old = sys.stderr
        sys.stderr = buf
        try:
            _DEFAULT.info("should not appear")
            _DEFAULT.error("should appear")
            # plain log() ignores level filters by design
            log("plain always appears")
        finally:
            sys.stderr = old
            set_level(old_level)
        out = buf.getvalue()
        self.assertNotIn("should not appear", out)
        self.assertIn("should appear", out)
        self.assertIn("plain always appears", out)


if __name__ == "__main__":
    unittest.main()

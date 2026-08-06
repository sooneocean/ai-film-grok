"""Tests for the project logger (P0-2, senior-dev quality plan).

``util/logger`` had zero dedicated tests; this starts covering the shared
observability entry point.
"""

from __future__ import annotations

import io
import logging
import sys

from util import logger as logger_mod


def _shared_stream_handler() -> logging.StreamHandler:
    handler = next(
        (h for h in logger_mod.log.handlers if isinstance(h, logging.StreamHandler)),
        None,
    )
    assert handler is not None, "aifilm logger must have a StreamHandler"
    return handler


def test_logger_emits_and_routes_to_stderr() -> None:
    handler = _shared_stream_handler()
    buf = io.StringIO()
    original = handler.stream
    handler.stream = buf
    try:
        logger_mod.log.setLevel(logging.INFO)
        logger_mod.log.info("hello-from-aifilm")
        assert "hello-from-aifilm" in buf.getvalue()
    finally:
        handler.stream = original
    # The shared handler must NOT target stdout, so it cannot corrupt the JSON
    # API output that some CLI commands emit on stdout.
    assert original is not sys.stdout


def test_set_level_adjusts_runtime_level() -> None:
    logger_mod.set_level("ERROR")
    try:
        assert logger_mod.log.level == logging.ERROR
    finally:
        logger_mod.set_level("WARNING")

"""Project logging entry point (P0-2, senior-dev quality plan).

Dependency-free (does NOT import aifilm_grok) so any module — including
``util/*`` — can use it without creating a circular import.

Design rule: **library logs go to stderr**, never stdout. Many CLI commands
emit JSON on stdout as their API contract; routing logs to stdout would corrupt
that pipe. Use ``log.debug(structure)`` for structured diagnostics instead of
``print(json.dumps(...))`` in library code.
"""

from __future__ import annotations

import logging
import os
import sys

_LOG_NAME = "aifilm"


def _level_from_env() -> int:
    raw = os.environ.get("AIFILM_LOG_LEVEL", "WARNING").strip().upper()
    return getattr(logging, raw, logging.WARNING)


def _build_logger() -> logging.Logger:
    logger = logging.getLogger(_LOG_NAME)
    if logger.handlers:
        return logger
    handler: logging.Handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
    )
    logger.addHandler(handler)
    logger.setLevel(_level_from_env())
    logger.propagate = False
    return logger


log = _build_logger()


def set_level(level: str | int) -> None:
    """Adjust the aifilm logger level at runtime (used by CLI ``--verbose``)."""
    if isinstance(level, str):
        level = getattr(logging, level.strip().upper(), logging.WARNING)
    log.setLevel(level)
    for handler in log.handlers:
        handler.setLevel(level)

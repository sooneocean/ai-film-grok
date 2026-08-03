#!/usr/bin/env python3
"""Unified structured logger for ai-film-grok.

Usage:
    from logger import log, get_logger, set_level, LogLevel

    log("info message")                          # backward-compatible, level=INFO
    logger = get_logger("mymodule")
    logger.info("msg")                           # explicit module
    logger.debug("debug only")
    logger.warn("warning")
    logger.error("error")
    set_level(LogLevel.DEBUG)                    # change verbosity
    logger.count("api_calls", tags={"endpoint": "/v1"})
    print(logger.counts())                       # {"api_calls": 1, ...}
"""

from __future__ import annotations

import dataclasses
import enum
import inspect
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class LogLevel(enum.Enum):
    DEBUG = 10
    INFO = 20
    WARN = 30
    ERROR = 40


_LOG_LEVEL_NAMES: dict[str, LogLevel] = {m.name: m for m in LogLevel}


def _resolve_log_level(s: str) -> LogLevel:
    try:
        return _LOG_LEVEL_NAMES[s.upper().strip()]
    except KeyError:
        return LogLevel.INFO


@dataclasses.dataclass
class LogRecord:
    timestamp: str
    level: str
    module: str
    message: str
    extra: dict[str, Any] | None = None


class Logger:
    def __init__(self, name: str | None = None, level: LogLevel = LogLevel.INFO):
        self._name = name
        self._level = level
        self._human = os.environ.get("AIFILM_LOG_FORMAT", "").strip().lower() == "human"
        self._counts: dict[str, int] = {}

    def set_level(self, level: LogLevel) -> None:
        self._level = level

    def _caller_module(self) -> str:
        frame = inspect.currentframe()
        for _ in range(4):
            frame = frame.f_back if frame else None
        if frame is not None:
            mod = inspect.getmodule(frame)
            if mod is not None and mod.__file__ is not None:
                return Path(mod.__file__).stem
        return "unknown"

    def _write(self, level: LogLevel, msg: str, extra: dict[str, Any] | None = None) -> None:
        if level.value < self._level.value:
            return
        module = self._name if self._name else self._caller_module()
        record = LogRecord(
            timestamp=datetime.now(UTC).isoformat(),
            level=level.name,
            module=module,
            message=msg,
            extra=extra,
        )
        if self._human:
            line = f"[{record.level}] [{record.module}] {record.message}"
            if record.extra:
                line += f" {json.dumps(record.extra, ensure_ascii=False)}"
        else:
            d: dict[str, Any] = {
                "timestamp": record.timestamp,
                "level": record.level,
                "module": record.module,
                "message": record.message,
            }
            if record.extra:
                d["extra"] = record.extra
            line = json.dumps(d, ensure_ascii=False)
        print(line, file=sys.stderr, flush=True)

    def debug(self, msg: str, extra: dict[str, Any] | None = None) -> None:
        self._write(LogLevel.DEBUG, msg, extra)

    def info(self, msg: str, extra: dict[str, Any] | None = None) -> None:
        self._write(LogLevel.INFO, msg, extra)

    def warn(self, msg: str, extra: dict[str, Any] | None = None) -> None:
        self._write(LogLevel.WARN, msg, extra)

    def error(self, msg: str, extra: dict[str, Any] | None = None) -> None:
        self._write(LogLevel.ERROR, msg, extra)

    def count(self, name: str, delta: int = 1, tags: dict[str, str] | None = None) -> None:
        self._counts[name] = self._counts.get(name, 0) + delta

    def counts(self) -> dict[str, int]:
        return dict(self._counts)


_DEFAULT: Logger = Logger()


def log(msg: str) -> None:
    """Backward-compatible plain stderr line (not JSON).

    Historical callers (render_final / aifilm_grok / compose_*) expect a single
    human-readable line on stderr. Structured JSON goes through ``get_logger``.
    """
    print(msg, file=sys.stderr, flush=True)


def set_level(level: LogLevel) -> None:
    _DEFAULT.set_level(level)


def get_logger(name: str) -> Logger:
    return Logger(name=name)

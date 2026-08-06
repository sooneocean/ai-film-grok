"""logger.log stays plain-stderr compatible."""

from __future__ import annotations

import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from logger import get_logger, log  # noqa: E402


def test_log_is_plain_not_json(capsys=None) -> None:
    buf = io.StringIO()
    old = sys.stderr
    sys.stderr = buf
    try:
        log("hello-plain")
    finally:
        sys.stderr = old
    out = buf.getvalue()
    assert "hello-plain" in out
    assert not out.strip().startswith("{")


def test_get_logger_still_json() -> None:
    buf = io.StringIO()
    old = sys.stderr
    sys.stderr = buf
    try:
        get_logger("t").info("structured")
    finally:
        sys.stderr = old
    out = buf.getvalue()
    assert "structured" in out
    assert out.strip().startswith("{")

"""P4-1: first unit tests for core.emit (zero-coverage foundation)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from core.emit import emit  # noqa: E402


def test_emit_compact_when_not_tty(monkeypatch, capsys) -> None:
    monkeypatch.delenv("AIFILM_PRETTY_JSON", raising=False)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: False)
    emit({"ok": True, "n": 1})
    out = capsys.readouterr().out.strip()
    assert out == json.dumps({"ok": True, "n": 1}, ensure_ascii=False, separators=(",", ":"))
    assert "\n" not in out


def test_emit_pretty_when_tty(monkeypatch, capsys) -> None:
    monkeypatch.delenv("AIFILM_PRETTY_JSON", raising=False)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    emit({"ok": True})
    out = capsys.readouterr().out
    assert "\n" in out
    assert json.loads(out) == {"ok": True}


def test_emit_pretty_when_env_forces(monkeypatch, capsys) -> None:
    monkeypatch.setenv("AIFILM_PRETTY_JSON", "1")
    monkeypatch.setattr(sys.stdout, "isatty", lambda: False)
    emit({"a": 1})
    out = capsys.readouterr().out
    assert json.loads(out) == {"a": 1}
    assert "  " in out or "\n" in out

"""P4-3: unit tests for core.emit (zero-coverage foundation, merged from parallel agents)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from core.emit import emit  # noqa: E402


def test_emit_compact_by_default(capsys, monkeypatch):
    # Not a TTY (capsys captures) and no env -> compact single-line output.
    monkeypatch.delenv("AIFILM_PRETTY_JSON", raising=False)
    emit({"a": 1})
    assert capsys.readouterr().out == '{"a":1}\n'


def test_emit_compact_no_spaces(capsys, monkeypatch):
    monkeypatch.delenv("AIFILM_PRETTY_JSON", raising=False)
    emit({"x": [1, 2], "y": {"z": 3}})
    out = capsys.readouterr().out
    assert " " not in out
    assert out == '{"x":[1,2],"y":{"z":3}}\n'


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


def test_emit_pretty_with_env_1(capsys, monkeypatch):
    monkeypatch.setenv("AIFILM_PRETTY_JSON", "1")
    emit({"a": 1})
    out = capsys.readouterr().out
    assert "\n" in out and "  " in out  # indent=2
    assert json.loads(out) == {"a": 1}


def test_emit_pretty_env_variants(capsys, monkeypatch):
    for val in ("1", "true", "yes", "on"):
        monkeypatch.setenv("AIFILM_PRETTY_JSON", val)
        emit({"k": "v"})
        out = capsys.readouterr().out
        assert "\n" in out
        assert json.loads(out) == {"k": "v"}


def test_emit_pretty_when_env_forces(monkeypatch, capsys) -> None:
    monkeypatch.setenv("AIFILM_PRETTY_JSON", "1")
    monkeypatch.setattr(sys.stdout, "isatty", lambda: False)
    emit({"a": 1})
    out = capsys.readouterr().out
    assert json.loads(out) == {"a": 1}
    assert "  " in out or "\n" in out


def test_emit_preserves_unicode(capsys, monkeypatch):
    monkeypatch.delenv("AIFILM_PRETTY_JSON", raising=False)
    emit({"name": "霓虹"})
    out = capsys.readouterr().out
    assert "霓虹" in out  # ensure_ascii=False
    assert json.loads(out) == {"name": "霓虹"}


def test_emit_roundtrip_nested(capsys, monkeypatch):
    monkeypatch.setenv("AIFILM_PRETTY_JSON", "true")
    data = {"shots": [{"id": "s01", "dur": 6}, {"id": "s02"}], "meta": {"ok": True}}
    emit(data)
    assert json.loads(capsys.readouterr().out) == data


def test_emit_empty_dict(capsys, monkeypatch):
    monkeypatch.delenv("AIFILM_PRETTY_JSON", raising=False)
    emit({})
    assert capsys.readouterr().out == '{}\n'


def test_emit_env_off_stays_compact(capsys, monkeypatch):
    # Explicitly "off" must NOT pretty-print; only 1/true/yes/on count.
    monkeypatch.setenv("AIFILM_PRETTY_JSON", "0")
    emit({"a": 1})
    assert capsys.readouterr().out == '{"a":1}\n'

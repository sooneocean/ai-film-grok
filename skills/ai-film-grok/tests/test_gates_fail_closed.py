"""H2 · fail-closed gates + silent-except eradication (observability).

Locks the invariant that correctness gates FAIL CLOSED (raise ``ProductionGateError``
instead of silently returning ``{ok: True}``), and that best-effort fallbacks
degrade EXPLICITLY and emit a log line — never a silent swallow (``pass`` /
``return {}``).

Part of the project hardening plan (2026-08-08), Wave H2.
"""

from __future__ import annotations

import logging
import sys
import types

import pytest
import util
from gates.identity_generation_lock import _load_json as identity_load_json
from gates.partner_cast_gate import _load_json as partner_load_json
from production_gates import (
    ProductionGateError,
    _shot_would_stream_loop,
    assert_heat_allows_final,
)
from util.logger import log as aifilm_log


class _Capture(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


@pytest.fixture()
def captured(monkeypatch):
    cap = _Capture()
    prev_level = aifilm_log.level
    aifilm_log.addHandler(cap)
    aifilm_log.setLevel(logging.DEBUG)
    try:
        yield cap.records
    finally:
        aifilm_log.removeHandler(cap)
        aifilm_log.setLevel(prev_level)


def _stub_module(name: str, **attrs) -> types.ModuleType:
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    return mod


def test_heat_final_gate_fail_closed(monkeypatch, tmp_path):
    """A probe failure in the heat final gate MUST fail closed (raise), not pass."""

    def _boom(root):
        raise RuntimeError("probe down")

    monkeypatch.setitem(
        sys.modules, "heat_check", _stub_module("heat_check", heat_agent_status=_boom)
    )
    with pytest.raises(ProductionGateError):
        assert_heat_allows_final(tmp_path)


def test_identity_load_json_degrades_with_log(monkeypatch, captured, tmp_path):
    """_load_json must not silently swallow: it degrades to {} AND logs."""

    def _raiser(p):
        raise RuntimeError("boom")

    monkeypatch.setattr(util, "read_json", _raiser)
    out = identity_load_json(tmp_path / "missing.json")
    assert out == {}
    assert any("identity lock load failed" in r.getMessage() for r in captured)


def test_partner_load_json_degrades_with_log(monkeypatch, captured, tmp_path):
    """_load_json (partner cast) must degrade to {} AND log — never silent."""

    def _raiser(p):
        raise RuntimeError("boom")

    monkeypatch.setattr(util, "read_json", _raiser)
    out = partner_load_json(tmp_path / "missing.json")
    assert out == {}
    assert any("partner cast lock load failed" in r.getMessage() for r in captured)


def test_loop_risk_legacy_fallback_logs(monkeypatch, captured):
    """When edit_policy is unavailable, loop-risk falls back to the legacy
    threshold AND logs the degradation (no silent broad-except)."""

    def _boom(*_a, **_k):
        raise RuntimeError("no policy")

    monkeypatch.setitem(sys.modules, "edit_policy", _stub_module("edit_policy", plan_stretch=_boom))
    res = _shot_would_stream_loop(plate_sec=4.0, vo_sec=6.0, dramatic_function=None)
    assert isinstance(res, bool)
    assert any("loop-risk policy unavailable" in r.getMessage() for r in captured)

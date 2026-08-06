"""P0-4: render_final wall-clock watchdog (假死 / 超时防护)."""

from __future__ import annotations

import sys
import time
import types
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

pytestmark = pytest.mark.hotpath

from final.errors import RenderError  # noqa: E402
from post.render_final import RenderTimeoutError, _run_with_watchdog  # noqa: E402


def test_render_timeout_error_is_render_error() -> None:
    err = RenderTimeoutError(120.0)
    assert isinstance(err, RenderError)
    assert err.timeout == 120.0


def test_watchdog_disabled_passthrough() -> None:
    assert _run_with_watchdog(lambda: 7, timeout=0) == 7
    assert _run_with_watchdog(lambda: 7, timeout=None) == 7


def test_watchdog_fast_ok_without_signal(monkeypatch) -> None:
    # Force the non-SIGALRM (thread) branch to keep the test deterministic.
    fake_signal = types.SimpleNamespace()  # no SIGALRM attribute
    monkeypatch.setattr("post.render_final.signal", fake_signal)
    assert _run_with_watchdog(lambda: "ok", timeout=5) == "ok"


def test_watchdog_times_out_without_signal(monkeypatch) -> None:
    fake_signal = types.SimpleNamespace()  # no SIGALRM attribute
    monkeypatch.setattr("post.render_final.signal", fake_signal)
    with pytest.raises(RenderTimeoutError):
        _run_with_watchdog(lambda: time.sleep(1), timeout=0.2)

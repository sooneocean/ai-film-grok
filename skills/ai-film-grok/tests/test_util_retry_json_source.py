"""Contracts for util.retry + util.read_json_source (quality plan Q1)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from util import read_json_source
from util.errors import FilmError
from util.retry import retry_call


def test_retry_call_succeeds_after_transient_failures() -> None:
    state = {"n": 0}

    def flaky() -> str:
        state["n"] += 1
        if state["n"] < 3:
            raise RuntimeError("transient")
        return "ok"

    sleeps: list[float] = []
    assert retry_call(flaky, attempts=3, delay_sec=0.01, sleep=sleeps.append) == "ok"
    assert state["n"] == 3
    assert len(sleeps) == 2


def test_retry_call_exhausts() -> None:
    def always_fail() -> None:
        raise ValueError("nope")

    with pytest.raises(ValueError, match="nope"):
        retry_call(always_fail, attempts=2, delay_sec=0.0, sleep=lambda _: None)


def test_read_json_source_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "doc.json"
    payload = {"a": 1, "b": [2, 3]}
    path.write_text(json.dumps(payload), encoding="utf-8")
    raw, value = read_json_source(path)
    assert value == payload
    assert json.loads(raw) == payload


def test_read_json_source_rejects_non_object_array(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("42", encoding="utf-8")
    with pytest.raises(FilmError, match="object or array"):
        read_json_source(path)


def test_poll_until_success() -> None:
    from util.retry import poll_until

    state = {"n": 0}

    def tick() -> str | None:
        state["n"] += 1
        return "ok" if state["n"] >= 3 else None

    sleeps: list[float] = []
    assert poll_until(tick, timeout_sec=10.0, interval_sec=0.01, sleep=sleeps.append) == "ok"
    assert state["n"] == 3
    assert len(sleeps) == 2


def test_poll_until_timeout() -> None:
    from util.retry import poll_until

    with pytest.raises(TimeoutError):
        poll_until(lambda: None, timeout_sec=0.05, interval_sec=0.01, sleep=lambda _: None)


def test_parse_mean_volume_db() -> None:
    from core.media_ops import parse_max_volume_db, parse_mean_volume_db, parse_volume_stats

    assert parse_mean_volume_db("mean_volume: -22.5 dB") == pytest.approx(-22.5)
    assert parse_mean_volume_db("nope") is None
    text = "mean_volume: -18.0 dB\nmax_volume: -3.1 dB\n"
    assert parse_max_volume_db(text) == pytest.approx(-3.1)
    stats = parse_volume_stats(text)
    assert stats["mean_volume_db"] == pytest.approx(-18.0)
    assert stats["max_volume_db"] == pytest.approx(-3.1)

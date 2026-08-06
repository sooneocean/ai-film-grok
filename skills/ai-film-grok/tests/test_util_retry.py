"""Tests for util.retry (P4-1: cover the zero-coverage foundation).

All timing is faked via injectable sleep/clock so the suite is deterministic
and instant.
"""
from __future__ import annotations

import pytest

from util.retry import poll_until, retry_call


class _FakeSleep:
    def __init__(self) -> None:
        self.calls: list[float] = []

    def __call__(self, secs: float) -> None:
        self.calls.append(secs)


class _FakeClock:
    def __init__(self, step: float = 1.0) -> None:
        self.t = 0.0
        self.step = step

    def __call__(self) -> float:
        now = self.t
        self.t += self.step
        return now


def test_retry_call_succeeds_first_try():
    sleep = _FakeSleep()
    assert retry_call(lambda: 42, sleep=sleep) == 42
    assert sleep.calls == []


def test_retry_call_retries_until_success_with_backoff():
    sleep = _FakeSleep()
    calls = {"n": 0}

    def flaky() -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("boom")
        return "ok"

    result = retry_call(flaky, attempts=4, delay_sec=0.5, backoff=2.0, sleep=sleep)
    assert result == "ok"
    # waited before 2nd and 3rd attempt: 0.5 then 1.0
    assert sleep.calls == [0.5, 1.0]


def test_retry_call_raises_last_after_all_attempts():
    sleep = _FakeSleep()

    def always_fail() -> int:
        raise ValueError("nope")

    with pytest.raises(ValueError):
        retry_call(always_fail, attempts=3, sleep=sleep)
    assert len(sleep.calls) == 2  # one less than attempts


def test_retry_call_respects_retry_on():
    sleep = _FakeSleep()

    def wrong_type() -> int:
        raise KeyError("not retried")

    # KeyError is not in retry_on=(ValueError,), so it propagates immediately
    with pytest.raises(KeyError):
        retry_call(wrong_type, attempts=3, retry_on=(ValueError,), sleep=sleep)
    assert sleep.calls == []


def test_retry_call_rejects_bad_attempts():
    with pytest.raises(ValueError):
        retry_call(lambda: 1, attempts=0)


def test_poll_until_returns_value_when_ready():
    sleep = _FakeSleep()
    assert poll_until(lambda: "done", timeout_sec=5, sleep=sleep) == "done"
    assert sleep.calls == []


def test_poll_until_raises_timeout():
    sleep = _FakeSleep()
    clock = _FakeClock(step=1.0)
    with pytest.raises(TimeoutError):
        poll_until(lambda: None, timeout_sec=3, interval_sec=1, sleep=sleep, clock=clock)
    # clock() is also consumed once for the deadline, so 2 sleeps before timeout
    assert len(sleep.calls) == 2


def test_poll_until_validates_args():
    with pytest.raises(ValueError):
        poll_until(lambda: None, timeout_sec=0)
    with pytest.raises(ValueError):
        poll_until(lambda: None, timeout_sec=1, interval_sec=-1)

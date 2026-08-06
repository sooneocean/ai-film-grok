"""Shared retry / backoff helpers (single implementation for new call sites)."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


def retry_call(
    fn: Callable[[], T],
    *,
    attempts: int = 3,
    delay_sec: float = 0.5,
    backoff: float = 2.0,
    retry_on: tuple[type[BaseException], ...] = (Exception,),
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Call ``fn`` up to ``attempts`` times with exponential backoff.

    Raises the last exception if all attempts fail. ``attempts`` must be >= 1.
    """
    if attempts < 1:
        raise ValueError("attempts must be >= 1")
    last: BaseException | None = None
    wait = delay_sec
    for i in range(attempts):
        try:
            return fn()
        except retry_on as exc:
            last = exc
            if i + 1 >= attempts:
                break
            sleep(wait)
            wait *= backoff
    assert last is not None
    raise last


def poll_until(
    fn: Callable[[], T | None],
    *,
    timeout_sec: float,
    interval_sec: float = 1.0,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.time,
) -> T:
    """Call ``fn`` until it returns a non-``None`` value or ``timeout_sec`` elapses.

    ``fn`` should return ``None`` to mean "not ready yet". On timeout raises
    ``TimeoutError`` (last non-ready poll is not retained as a success value).
    """
    if timeout_sec <= 0:
        raise ValueError("timeout_sec must be > 0")
    if interval_sec < 0:
        raise ValueError("interval_sec must be >= 0")
    deadline = clock() + float(timeout_sec)
    while True:
        value = fn()
        if value is not None:
            return value
        now = clock()
        if now >= deadline:
            raise TimeoutError(f"poll_until timed out after {timeout_sec}s")
        remaining = deadline - now
        sleep(min(float(interval_sec), max(0.0, remaining)))

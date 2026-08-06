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

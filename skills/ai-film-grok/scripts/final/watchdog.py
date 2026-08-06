"""Final render wall-clock watchdog (M2 peel · 2026-08-06).

Extracted from post.render_final so orchestrator stays thinner.
Public re-export: ``render_final._run_with_watchdog``.
"""

from __future__ import annotations

import signal
from typing import TypeVar

from final.errors import RenderTimeoutError

T = TypeVar("T")


def _run_with_watchdog(func, *, timeout: float):
    """Run ``func`` under a total wall-clock watchdog.

    Individual ffmpeg / TTS subprocesses already carry their own per-call timeouts
    (AIFILM_FFMPEG_TIMEOUT, util.subprocess.run default). This guard caps the *total*
    render so a stalled pipeline surfaces a clean error instead of hanging forever
    (假死). On Unix we use SIGALRM (fires in the main thread, where render runs);
    on other platforms with no SIGALRM we fall back to a daemon thread that raises on
    breach. ``timeout <= 0`` disables the guard.
    """
    if timeout is None or timeout <= 0:
        return func()

    if hasattr(signal, "SIGALRM"):

        def _alarm_handler(signum, frame):  # pragma: no cover - signal path
            raise RenderTimeoutError(timeout)

        prev = signal.signal(signal.SIGALRM, _alarm_handler)
        try:
            signal.alarm(max(1, int(timeout)))
            return func()
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, prev)
    else:  # pragma: no cover - non-Unix fallback
        import threading

        # Thread-based watchdog for platforms without SIGALRM.
        holder: list[tuple[str, object] | None] = [None]

        def _target() -> None:
            try:
                holder[0] = ("result", func())
            except BaseException as exc:  # noqa: BLE001
                holder[0] = ("error", exc)

        t = threading.Thread(target=_target, daemon=True)
        t.start()
        t.join(timeout)
        if t.is_alive():
            raise RenderTimeoutError(timeout)
        item = holder[0]
        if item is None:
            raise RenderTimeoutError(timeout)
        if item[0] == "error":
            raise item[1]
        return item[1]



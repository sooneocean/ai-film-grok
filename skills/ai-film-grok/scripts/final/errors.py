"""Render-time errors for final delivery (W4 peel)."""

from __future__ import annotations

from util.errors import FilmError


class RenderError(FilmError):
    pass


class RenderTimeoutError(RenderError):
    """render_final exceeded its wall-clock budget (possible freeze / hang)."""

    def __init__(self, timeout: float) -> None:
        super().__init__(
            f"render_final exceeded --render-timeout={timeout:g}s without completing "
            "(possible freeze/hang). Per-subprocess ffmpeg calls carry their own timeouts "
            "(AIFILM_FFMPEG_TIMEOUT); this guard caps total wall-clock. Re-run with --resume "
            "or raise --render-timeout. Emergency escape: --render-timeout 0."
        )
        self.timeout = timeout


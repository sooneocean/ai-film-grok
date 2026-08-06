"""Shim — implementation in media.realesrgan_upscale."""

from __future__ import annotations

from media.realesrgan_upscale import *  # noqa: F403
from media.realesrgan_upscale import (  # noqa: F401
    DEFAULT_MODEL,
    DEFAULT_SCALE,
    UpscaleError,
    backend_status,
    film_upscale_enabled,
    fingerprint_assets,
    ffmpeg_geometry_upscale,
    plan_upscale,
    promote_upscale,
    run_canary_ab,
    run_upscale_batch,
    upscale_video,
)

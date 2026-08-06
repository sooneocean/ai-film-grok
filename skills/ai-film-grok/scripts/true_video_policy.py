"""Shim — implementation in media.true_video_policy (hard-compat).

Keeps `import true_video_policy` working after package move.
"""
from __future__ import annotations

from media import true_video_policy as _impl
import sys as _sys

_sys.modules[__name__] = _impl

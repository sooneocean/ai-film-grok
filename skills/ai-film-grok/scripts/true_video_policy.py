"""Shim — implementation in media.true_video_policy (hard-compat).

Keeps `import true_video_policy` working after package move.
"""
from __future__ import annotations

import sys as _sys

from media import true_video_policy as _impl

_sys.modules[__name__] = _impl

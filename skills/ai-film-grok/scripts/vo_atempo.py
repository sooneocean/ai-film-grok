"""Shim — implementation in audio.vo_atempo (hard-compat).

Keeps `import vo_atempo` working after package move.
"""
from __future__ import annotations

import sys as _sys

from audio import vo_atempo as _impl

_sys.modules[__name__] = _impl

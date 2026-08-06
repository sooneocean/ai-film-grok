"""Shim — implementation in audio.vo_atempo (hard-compat).

Keeps `import vo_atempo` working after package move.
"""
from __future__ import annotations

from audio import vo_atempo as _impl
import sys as _sys

_sys.modules[__name__] = _impl

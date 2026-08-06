"""Shim — implementation in plan.five_track (hard-compat).

Keeps `import five_track` working after package move.
"""
from __future__ import annotations

from plan import five_track as _impl
import sys as _sys

_sys.modules[__name__] = _impl

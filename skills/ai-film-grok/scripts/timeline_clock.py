"""Shim — implementation in plan.timeline_clock (hard-compat).

Keeps `import timeline_clock` working after package move.
"""
from __future__ import annotations

from plan import timeline_clock as _impl
import sys as _sys

_sys.modules[__name__] = _impl

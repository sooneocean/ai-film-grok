"""Shim — implementation in plan.performance_cue (hard-compat).

Keeps `import performance_cue` working after package move.
"""
from __future__ import annotations

from plan import performance_cue as _impl
import sys as _sys

_sys.modules[__name__] = _impl

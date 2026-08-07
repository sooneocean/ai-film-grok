"""Shim — implementation in plan.performance_cue (hard-compat).

Keeps `import performance_cue` working after package move.
"""
from __future__ import annotations

import sys as _sys

from plan import performance_cue as _impl

_sys.modules[__name__] = _impl

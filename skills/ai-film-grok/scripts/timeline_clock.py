"""Shim — implementation in plan.timeline_clock (hard-compat).

Keeps `import timeline_clock` working after package move.
"""
from __future__ import annotations

import sys as _sys

from plan import timeline_clock as _impl

_sys.modules[__name__] = _impl

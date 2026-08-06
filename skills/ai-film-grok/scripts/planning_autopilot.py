"""Shim — implementation in plan.planning_autopilot (hard-compat).

Keeps `import planning_autopilot` working after package move.
"""
from __future__ import annotations

from plan import planning_autopilot as _impl
import sys as _sys

_sys.modules[__name__] = _impl

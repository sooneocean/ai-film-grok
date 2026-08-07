"""Shim — implementation in plan.planning_autopilot (hard-compat).

Keeps `import planning_autopilot` working after package move.
"""
from __future__ import annotations

import sys as _sys

from plan import planning_autopilot as _impl

_sys.modules[__name__] = _impl

"""Shim — implementation in plan.motion_plan (hard-compat).

Keeps `import motion_plan` working after package move.
"""
from __future__ import annotations

from plan import motion_plan as _impl
import sys as _sys

_sys.modules[__name__] = _impl

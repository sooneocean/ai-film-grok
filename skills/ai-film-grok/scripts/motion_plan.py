"""Shim — implementation in plan.motion_plan (hard-compat).

Keeps `import motion_plan` working after package move.
"""
from __future__ import annotations

import sys as _sys

from plan import motion_plan as _impl

_sys.modules[__name__] = _impl

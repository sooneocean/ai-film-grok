"""Shim — implementation in plan.department_cli (hard-compat).

Keeps `import department_cli` working after package move.
"""
from __future__ import annotations

from plan import department_cli as _impl
import sys as _sys

_sys.modules[__name__] = _impl

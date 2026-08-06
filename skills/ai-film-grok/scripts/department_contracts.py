"""Shim — implementation in plan.department_contracts (hard-compat).

Keeps `import department_contracts` working after package move.
"""
from __future__ import annotations

from plan import department_contracts as _impl
import sys as _sys

_sys.modules[__name__] = _impl

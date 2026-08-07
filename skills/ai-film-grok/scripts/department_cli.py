"""Shim — implementation in plan.department_cli (hard-compat).

Keeps `import department_cli` working after package move.
"""
from __future__ import annotations

import sys as _sys

from plan import department_cli as _impl

_sys.modules[__name__] = _impl

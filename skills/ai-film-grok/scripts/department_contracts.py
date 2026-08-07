"""Shim — implementation in plan.department_contracts (hard-compat).

Keeps `import department_contracts` working after package move.
"""
from __future__ import annotations

import sys as _sys

from plan import department_contracts as _impl

_sys.modules[__name__] = _impl

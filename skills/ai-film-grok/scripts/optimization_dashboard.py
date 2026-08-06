"""Shim — implementation in plan.optimization_dashboard (hard-compat).

Keeps `import optimization_dashboard` working after package move.
"""
from __future__ import annotations

from plan import optimization_dashboard as _impl
import sys as _sys

_sys.modules[__name__] = _impl

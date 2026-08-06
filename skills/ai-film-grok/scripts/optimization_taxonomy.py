"""Shim — implementation in plan.optimization_taxonomy (hard-compat).

Keeps `import optimization_taxonomy` working after package move.
"""
from __future__ import annotations

from plan import optimization_taxonomy as _impl
import sys as _sys

_sys.modules[__name__] = _impl

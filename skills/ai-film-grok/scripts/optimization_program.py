"""Shim — implementation in plan.optimization_program (hard-compat).

Keeps `import optimization_program` working after package move.
"""
from __future__ import annotations

from plan import optimization_program as _impl
import sys as _sys

_sys.modules[__name__] = _impl

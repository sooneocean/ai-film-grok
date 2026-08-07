"""Shim — implementation in plan.optimization_metrics (hard-compat).

Keeps `import optimization_metrics` working after package move.
"""
from __future__ import annotations

from plan import optimization_metrics as _impl
import sys as _sys

_sys.modules[__name__] = _impl

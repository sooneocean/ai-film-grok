"""Shim — implementation in plan.optimization_experiments (hard-compat).

Keeps `import optimization_experiments` working after package move.
"""
from __future__ import annotations

from plan import optimization_experiments as _impl
import sys as _sys

_sys.modules[__name__] = _impl

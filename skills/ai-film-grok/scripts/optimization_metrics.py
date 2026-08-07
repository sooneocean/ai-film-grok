"""Shim — implementation in plan.optimization_metrics (hard-compat).

Keeps `import optimization_metrics` working after package move.
"""
from __future__ import annotations

import sys as _sys

from plan import optimization_metrics as _impl

_sys.modules[__name__] = _impl

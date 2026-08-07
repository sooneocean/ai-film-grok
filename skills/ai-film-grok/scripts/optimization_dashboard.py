"""Shim — implementation in plan.optimization_dashboard (hard-compat).

Keeps `import optimization_dashboard` working after package move.
"""
from __future__ import annotations

import sys as _sys

from plan import optimization_dashboard as _impl

_sys.modules[__name__] = _impl

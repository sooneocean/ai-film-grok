"""Shim — implementation in plan.optimization_taxonomy (hard-compat).

Keeps `import optimization_taxonomy` working after package move.
"""
from __future__ import annotations

import sys as _sys

from plan import optimization_taxonomy as _impl

_sys.modules[__name__] = _impl

"""Shim — implementation in plan.optimization_program (hard-compat).

Keeps `import optimization_program` working after package move.
"""
from __future__ import annotations

import sys as _sys

from plan import optimization_program as _impl

_sys.modules[__name__] = _impl

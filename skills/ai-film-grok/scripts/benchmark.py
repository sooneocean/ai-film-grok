"""Shim — implementation in plan.benchmark (hard-compat).

Keeps `import benchmark` working after package move.
"""
from __future__ import annotations

from plan import benchmark as _impl
import sys as _sys

_sys.modules[__name__] = _impl

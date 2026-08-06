"""Shim — implementation in plan.quality_closure (hard-compat).

Keeps `import quality_closure` working after package move.
"""
from __future__ import annotations

from plan import quality_closure as _impl
import sys as _sys

_sys.modules[__name__] = _impl

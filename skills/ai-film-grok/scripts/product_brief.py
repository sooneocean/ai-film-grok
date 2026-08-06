"""Shim — implementation in plan.product_brief (hard-compat).

Keeps `import product_brief` working after package move.
"""
from __future__ import annotations

from plan import product_brief as _impl
import sys as _sys

_sys.modules[__name__] = _impl

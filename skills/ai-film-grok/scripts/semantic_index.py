"""Shim — implementation in plan.semantic_index (hard-compat).

Keeps `import semantic_index` working after package move.
"""
from __future__ import annotations

from plan import semantic_index as _impl
import sys as _sys

_sys.modules[__name__] = _impl

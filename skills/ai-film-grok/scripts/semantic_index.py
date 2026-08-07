"""Shim — implementation in plan.semantic_index (hard-compat).

Keeps `import semantic_index` working after package move.
"""
from __future__ import annotations

import sys as _sys

from plan import semantic_index as _impl

_sys.modules[__name__] = _impl

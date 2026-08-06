"""Shim — implementation in plan.creative_workshop (hard-compat).

Keeps `import creative_workshop` working after package move.
"""
from __future__ import annotations

from plan import creative_workshop as _impl
import sys as _sys

_sys.modules[__name__] = _impl

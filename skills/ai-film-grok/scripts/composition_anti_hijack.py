"""Shim — implementation in plan.composition_anti_hijack (hard-compat).

Keeps `import composition_anti_hijack` working after package move.
"""
from __future__ import annotations

from plan import composition_anti_hijack as _impl
import sys as _sys

_sys.modules[__name__] = _impl

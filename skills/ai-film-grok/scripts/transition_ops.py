"""Shim — implementation in plan.transition_ops (hard-compat).

Keeps `import transition_ops` working after package move.
"""
from __future__ import annotations

from plan import transition_ops as _impl
import sys as _sys

_sys.modules[__name__] = _impl

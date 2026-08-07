"""Shim — implementation in plan.transition_ops (hard-compat).

Keeps `import transition_ops` working after package move.
"""
from __future__ import annotations

import sys as _sys

from plan import transition_ops as _impl

_sys.modules[__name__] = _impl

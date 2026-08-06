"""Shim — implementation in gates.state_index_gate (hard-compat).

Keeps `import state_index_gate` working after package move.
"""
from __future__ import annotations

from gates import state_index_gate as _impl
import sys as _sys

_sys.modules[__name__] = _impl

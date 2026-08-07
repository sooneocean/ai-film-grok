"""Shim — implementation in gates.state_index_gate (hard-compat).

Keeps `import state_index_gate` working after package move.
"""
from __future__ import annotations

import sys as _sys

from gates import state_index_gate as _impl

_sys.modules[__name__] = _impl

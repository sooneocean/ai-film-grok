"""Shim — implementation in gates.input_fidelity (hard-compat).

Keeps `import input_fidelity` working after package move.
"""
from __future__ import annotations

from gates import input_fidelity as _impl
import sys as _sys

_sys.modules[__name__] = _impl

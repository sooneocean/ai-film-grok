"""Shim — implementation in gates.input_fidelity (hard-compat).

Keeps `import input_fidelity` working after package move.
"""
from __future__ import annotations

import sys as _sys

from gates import input_fidelity as _impl

_sys.modules[__name__] = _impl

"""Shim — implementation in gates.golden_suite (hard-compat).

Keeps `import golden_suite` working after package move.
"""
from __future__ import annotations

from gates import golden_suite as _impl
import sys as _sys

_sys.modules[__name__] = _impl

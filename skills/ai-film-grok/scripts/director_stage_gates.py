"""Shim — implementation in gates.director_stage_gates (hard-compat).

Keeps `import director_stage_gates` working after package move.
"""
from __future__ import annotations

from gates import director_stage_gates as _impl
import sys as _sys

_sys.modules[__name__] = _impl

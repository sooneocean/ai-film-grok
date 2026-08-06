"""Shim — implementation in plan.director_cli (hard-compat).

Keeps `import director_cli` working after package move.
"""
from __future__ import annotations

from plan import director_cli as _impl
import sys as _sys

_sys.modules[__name__] = _impl

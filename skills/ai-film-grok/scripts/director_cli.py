"""Shim — implementation in plan.director_cli (hard-compat).

Keeps `import director_cli` working after package move.
"""
from __future__ import annotations

import sys as _sys

from plan import director_cli as _impl

_sys.modules[__name__] = _impl

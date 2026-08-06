"""Shim — implementation in plan.director_ledger (hard-compat).

Keeps `import director_ledger` working after package move.
"""
from __future__ import annotations

from plan import director_ledger as _impl
import sys as _sys

_sys.modules[__name__] = _impl

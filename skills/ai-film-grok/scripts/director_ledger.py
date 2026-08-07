"""Shim — implementation in plan.director_ledger (hard-compat).

Keeps `import director_ledger` working after package move.
"""
from __future__ import annotations

import sys as _sys

from plan import director_ledger as _impl

_sys.modules[__name__] = _impl

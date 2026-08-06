"""Shim — implementation in plan.quality_ledger (hard-compat).

Keeps `import quality_ledger` working after package move.
"""
from __future__ import annotations

from plan import quality_ledger as _impl
import sys as _sys

_sys.modules[__name__] = _impl

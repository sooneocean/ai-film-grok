"""Shim — implementation in plan.quality_ledger (hard-compat).

Keeps `import quality_ledger` working after package move.
"""
from __future__ import annotations

import sys as _sys

from plan import quality_ledger as _impl

_sys.modules[__name__] = _impl

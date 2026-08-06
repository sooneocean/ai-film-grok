"""Shim — implementation in plan.evidence_status (hard-compat).

Keeps `import evidence_status` working after package move.
"""
from __future__ import annotations

from plan import evidence_status as _impl
import sys as _sys

_sys.modules[__name__] = _impl

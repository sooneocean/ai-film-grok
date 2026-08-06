"""Shim — implementation in plan.plan_feedback (hard-compat).

Keeps `import plan_feedback` working after package move.
"""
from __future__ import annotations

from plan import plan_feedback as _impl
import sys as _sys

_sys.modules[__name__] = _impl

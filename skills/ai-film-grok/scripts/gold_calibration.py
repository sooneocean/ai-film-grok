"""Shim — implementation in plan.gold_calibration (hard-compat).

Keeps `import gold_calibration` working after package move.
"""
from __future__ import annotations

from plan import gold_calibration as _impl
import sys as _sys

_sys.modules[__name__] = _impl

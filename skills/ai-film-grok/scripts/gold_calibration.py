"""Shim — implementation in plan.gold_calibration (hard-compat).

Keeps `import gold_calibration` working after package move.
"""
from __future__ import annotations

import sys as _sys

from plan import gold_calibration as _impl

_sys.modules[__name__] = _impl

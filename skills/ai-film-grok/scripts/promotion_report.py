"""Shim — implementation in plan.promotion_report (hard-compat).

Keeps `import promotion_report` working after package move.
"""
from __future__ import annotations

import sys as _sys

from plan import promotion_report as _impl

_sys.modules[__name__] = _impl

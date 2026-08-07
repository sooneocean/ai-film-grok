"""Shim — implementation in plan.capability_report (hard-compat).

Keeps `import capability_report` working after package move.
"""
from __future__ import annotations

import sys as _sys

from plan import capability_report as _impl

_sys.modules[__name__] = _impl

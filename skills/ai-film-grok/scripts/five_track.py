"""Shim — implementation in plan.five_track (hard-compat).

Keeps `import five_track` working after package move.
"""
from __future__ import annotations

import sys as _sys

from plan import five_track as _impl

_sys.modules[__name__] = _impl

"""Shim — implementation in plan.quality_check_video (hard-compat).

Keeps `import quality_check_video` working after package move.
"""
from __future__ import annotations

from plan import quality_check_video as _impl
import sys as _sys

_sys.modules[__name__] = _impl

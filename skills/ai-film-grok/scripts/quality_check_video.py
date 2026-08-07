"""Shim — implementation in plan.quality_check_video (hard-compat).

Keeps `import quality_check_video` working after package move.
"""
from __future__ import annotations

import sys as _sys

from plan import quality_check_video as _impl

_sys.modules[__name__] = _impl

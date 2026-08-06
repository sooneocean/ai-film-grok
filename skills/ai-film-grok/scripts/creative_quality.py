"""Shim — implementation in plan.creative_quality (hard-compat).

Keeps `import creative_quality` working after package move.
"""
from __future__ import annotations

from plan import creative_quality as _impl
import sys as _sys

_sys.modules[__name__] = _impl

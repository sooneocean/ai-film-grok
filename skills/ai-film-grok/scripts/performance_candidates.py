"""Shim — implementation in media.performance_candidates (hard-compat).

Keeps `import performance_candidates` working after package move.
"""
from __future__ import annotations

from media import performance_candidates as _impl
import sys as _sys

_sys.modules[__name__] = _impl

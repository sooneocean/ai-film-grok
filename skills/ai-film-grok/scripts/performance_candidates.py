"""Shim — implementation in media.performance_candidates (hard-compat).

Keeps `import performance_candidates` working after package move.
"""
from __future__ import annotations

import sys as _sys

from media import performance_candidates as _impl

_sys.modules[__name__] = _impl

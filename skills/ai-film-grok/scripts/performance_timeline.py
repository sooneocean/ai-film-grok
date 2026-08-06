"""Shim — implementation in post.performance_timeline (hard-compat).

Keeps `import performance_timeline` working after package move.
"""
from __future__ import annotations

from post import performance_timeline as _impl
import sys as _sys

_sys.modules[__name__] = _impl

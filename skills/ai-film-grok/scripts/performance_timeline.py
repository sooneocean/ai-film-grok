"""Shim — implementation in post.performance_timeline (hard-compat).

Keeps `import performance_timeline` working after package move.
"""
from __future__ import annotations

import sys as _sys

from post import performance_timeline as _impl

_sys.modules[__name__] = _impl

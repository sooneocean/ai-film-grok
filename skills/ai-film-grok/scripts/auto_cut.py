"""Shim — implementation in post.auto_cut (hard-compat).

Keeps `import auto_cut` working after package move.
"""
from __future__ import annotations

from post import auto_cut as _impl
import sys as _sys

_sys.modules[__name__] = _impl

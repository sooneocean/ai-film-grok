"""Shim — implementation in post.dailies (hard-compat).

Keeps `import dailies` working after package move.
"""
from __future__ import annotations

from post import dailies as _impl
import sys as _sys

_sys.modules[__name__] = _impl

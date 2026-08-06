"""Shim — implementation in post.picture_lock (hard-compat).

Keeps `import picture_lock` working after package move.
"""
from __future__ import annotations

from post import picture_lock as _impl
import sys as _sys

_sys.modules[__name__] = _impl

"""Shim — implementation in post.color_grade (hard-compat).

Keeps `import color_grade` working after package move.
"""
from __future__ import annotations

from post import color_grade as _impl
import sys as _sys

_sys.modules[__name__] = _impl

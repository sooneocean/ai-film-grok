"""Shim — implementation in post.color_grade (hard-compat).

Keeps `import color_grade` working after package move.
"""
from __future__ import annotations

import sys as _sys

from post import color_grade as _impl

_sys.modules[__name__] = _impl

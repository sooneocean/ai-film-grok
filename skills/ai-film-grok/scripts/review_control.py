"""Shim — implementation in post.review_control (hard-compat).

Keeps `import review_control` working after package move.
"""
from __future__ import annotations

from post import review_control as _impl
import sys as _sys

_sys.modules[__name__] = _impl

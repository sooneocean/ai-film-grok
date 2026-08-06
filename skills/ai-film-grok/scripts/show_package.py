"""Shim — implementation in post.show_package (hard-compat).

Keeps `import show_package` working after package move.
"""
from __future__ import annotations

from post import show_package as _impl
import sys as _sys

_sys.modules[__name__] = _impl

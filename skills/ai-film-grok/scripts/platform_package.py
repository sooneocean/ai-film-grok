"""Shim — implementation in post.platform_package (hard-compat).

Keeps `import platform_package` working after package move.
"""
from __future__ import annotations

from post import platform_package as _impl
import sys as _sys

_sys.modules[__name__] = _impl

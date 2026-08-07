"""Shim — implementation in post.platform_package (hard-compat).

Keeps `import platform_package` working after package move.
"""
from __future__ import annotations

import sys as _sys

from post import platform_package as _impl

_sys.modules[__name__] = _impl

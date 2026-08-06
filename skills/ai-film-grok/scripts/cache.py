"""Shim — implementation in media.cache (hard-compat).

Keeps `import cache` working after package move.
"""
from __future__ import annotations

from media import cache as _impl
import sys as _sys

_sys.modules[__name__] = _impl

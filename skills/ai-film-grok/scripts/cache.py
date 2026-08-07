"""Shim — implementation in media.cache (hard-compat).

Keeps `import cache` working after package move.
"""
from __future__ import annotations

import sys as _sys

from media import cache as _impl

_sys.modules[__name__] = _impl

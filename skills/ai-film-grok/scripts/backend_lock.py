"""Shim — implementation in media.backend_lock (hard-compat).

Keeps `import backend_lock` working after package move.
"""
from __future__ import annotations

from media import backend_lock as _impl
import sys as _sys

_sys.modules[__name__] = _impl

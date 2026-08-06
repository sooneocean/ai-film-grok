"""Shim — implementation in media.real_footage (hard-compat).

Keeps `import real_footage` working after package move.
"""
from __future__ import annotations

from media import real_footage as _impl
import sys as _sys

_sys.modules[__name__] = _impl

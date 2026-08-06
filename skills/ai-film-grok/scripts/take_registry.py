"""Shim — implementation in media.take_registry (hard-compat).

Keeps `import take_registry` working after package move.
"""
from __future__ import annotations

from media import take_registry as _impl
import sys as _sys

_sys.modules[__name__] = _impl

"""Shim — implementation in narrative.rhythm (hard-compat).

Keeps `import rhythm` working after package move.
"""
from __future__ import annotations

from narrative import rhythm as _impl
import sys as _sys

_sys.modules[__name__] = _impl

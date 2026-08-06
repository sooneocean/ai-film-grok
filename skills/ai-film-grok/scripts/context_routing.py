"""Shim — implementation in spine.context_routing (hard-compat).

Keeps `import context_routing` working after package move.
"""
from __future__ import annotations

from spine import context_routing as _impl
import sys as _sys

_sys.modules[__name__] = _impl

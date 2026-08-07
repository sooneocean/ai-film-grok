"""Shim — implementation in spine.route_catalog (hard-compat).

Keeps `import route_catalog` working after package move.
"""
from __future__ import annotations

from spine import route_catalog as _impl
import sys as _sys

_sys.modules[__name__] = _impl

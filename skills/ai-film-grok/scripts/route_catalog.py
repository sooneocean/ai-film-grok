"""Shim — implementation in spine.route_catalog (hard-compat).

Keeps `import route_catalog` working after package move.
"""
from __future__ import annotations

import sys as _sys

from spine import route_catalog as _impl

_sys.modules[__name__] = _impl

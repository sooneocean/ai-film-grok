"""Shim — implementation in web.projection (hard-compat).

Keeps `import console_projection` working after package move.
"""
from __future__ import annotations

import sys as _sys

from web import projection as _impl

_sys.modules[__name__] = _impl

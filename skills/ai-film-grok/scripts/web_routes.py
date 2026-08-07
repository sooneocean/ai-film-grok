"""Shim — implementation in web.routes (hard-compat).

Keeps `import web_routes` working after package move.
"""
from __future__ import annotations

import sys as _sys

from web import routes as _impl

_sys.modules[__name__] = _impl

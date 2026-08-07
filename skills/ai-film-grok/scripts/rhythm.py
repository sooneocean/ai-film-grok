"""Shim — implementation in narrative.rhythm (hard-compat).

Keeps `import rhythm` working after package move.
"""
from __future__ import annotations

import sys as _sys

from narrative import rhythm as _impl

_sys.modules[__name__] = _impl

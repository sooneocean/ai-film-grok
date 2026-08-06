"""Shim — implementation in post.master_delivery (hard-compat).

Keeps `import master_delivery` working after package move.
"""
from __future__ import annotations

from post import master_delivery as _impl
import sys as _sys

_sys.modules[__name__] = _impl

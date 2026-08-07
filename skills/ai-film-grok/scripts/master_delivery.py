"""Shim — implementation in post.master_delivery (hard-compat).

Keeps `import master_delivery` working after package move.
"""
from __future__ import annotations

import sys as _sys

from post import master_delivery as _impl

_sys.modules[__name__] = _impl

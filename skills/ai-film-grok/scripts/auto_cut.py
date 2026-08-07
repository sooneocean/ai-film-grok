"""Shim — implementation in post.auto_cut (hard-compat).

Keeps `import auto_cut` working after package move.
"""
from __future__ import annotations

import sys as _sys

from post import auto_cut as _impl

_sys.modules[__name__] = _impl

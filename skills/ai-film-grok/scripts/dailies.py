"""Shim — implementation in post.dailies (hard-compat).

Keeps `import dailies` working after package move.
"""
from __future__ import annotations

import sys as _sys

from post import dailies as _impl

_sys.modules[__name__] = _impl

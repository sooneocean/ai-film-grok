"""Shim — implementation in post.picture_lock (hard-compat).

Keeps `import picture_lock` working after package move.
"""
from __future__ import annotations

import sys as _sys

from post import picture_lock as _impl

_sys.modules[__name__] = _impl

"""Shim — implementation in post.review_pack (hard-compat).

Keeps `import review_pack` working after package move.
"""
from __future__ import annotations

import sys as _sys

from post import review_pack as _impl

_sys.modules[__name__] = _impl

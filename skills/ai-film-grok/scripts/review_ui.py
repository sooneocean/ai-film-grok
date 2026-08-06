"""Shim — implementation in post.review_ui (hard-compat).

Keeps `import review_ui` working after package move.
"""
from __future__ import annotations

from post import review_ui as _impl
import sys as _sys

_sys.modules[__name__] = _impl

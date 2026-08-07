"""Shim — implementation in post.review_ui (hard-compat).

Keeps `import review_ui` working after package move.
"""
from __future__ import annotations

import sys as _sys

from post import review_ui as _impl

_sys.modules[__name__] = _impl

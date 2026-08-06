"""Shim — implementation in post.external_review (hard-compat).

Keeps `import external_review` working after package move.
"""
from __future__ import annotations

from post import external_review as _impl
import sys as _sys

_sys.modules[__name__] = _impl

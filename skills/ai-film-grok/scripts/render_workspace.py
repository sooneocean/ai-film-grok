"""Shim — implementation in post.render_workspace (hard-compat).

Keeps `import render_workspace` working after package move.
"""
from __future__ import annotations

from post import render_workspace as _impl
import sys as _sys

_sys.modules[__name__] = _impl

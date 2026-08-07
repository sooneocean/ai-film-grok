"""Shim — implementation in post.render_workspace (hard-compat).

Keeps `import render_workspace` working after package move.
"""
from __future__ import annotations

import sys as _sys

from post import render_workspace as _impl

_sys.modules[__name__] = _impl

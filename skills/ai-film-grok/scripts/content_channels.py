"""Shim — implementation in plan.content_channels (hard-compat).

Keeps `import content_channels` working after package move.
"""
from __future__ import annotations

from plan import content_channels as _impl
import sys as _sys

_sys.modules[__name__] = _impl

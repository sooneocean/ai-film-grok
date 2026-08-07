"""Shim — implementation in plan.content_channels (hard-compat).

Keeps `import content_channels` working after package move.
"""
from __future__ import annotations

import sys as _sys

from plan import content_channels as _impl

_sys.modules[__name__] = _impl

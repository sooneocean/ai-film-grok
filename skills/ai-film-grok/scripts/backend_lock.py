"""Shim — implementation in media.backend_lock (hard-compat).

Keeps `import backend_lock` working after package move.
"""
from __future__ import annotations

import sys as _sys

from media import backend_lock as _impl

_sys.modules[__name__] = _impl

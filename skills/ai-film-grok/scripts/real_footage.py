"""Shim — implementation in media.real_footage (hard-compat).

Keeps `import real_footage` working after package move.
"""
from __future__ import annotations

import sys as _sys

from media import real_footage as _impl

_sys.modules[__name__] = _impl

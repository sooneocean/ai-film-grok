"""Shim — implementation in media.provider_canary (hard-compat).

Keeps `import provider_canary` working after package move.
"""
from __future__ import annotations

from media import provider_canary as _impl
import sys as _sys

_sys.modules[__name__] = _impl

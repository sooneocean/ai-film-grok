"""Shim — implementation in media.provider_canary (hard-compat).

Keeps `import provider_canary` working after package move.
"""
from __future__ import annotations

import sys as _sys

from media import provider_canary as _impl

_sys.modules[__name__] = _impl

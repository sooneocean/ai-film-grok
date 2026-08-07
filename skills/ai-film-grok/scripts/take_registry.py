"""Shim — implementation in media.take_registry (hard-compat).

Keeps `import take_registry` working after package move.
"""
from __future__ import annotations

import sys as _sys

from media import take_registry as _impl

_sys.modules[__name__] = _impl

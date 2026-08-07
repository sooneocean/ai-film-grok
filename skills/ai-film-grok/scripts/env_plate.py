"""Shim — implementation in media.env_plate (hard-compat).

Keeps `import env_plate` working after package move.
"""
from __future__ import annotations

from media import env_plate as _impl
import sys as _sys

_sys.modules[__name__] = _impl

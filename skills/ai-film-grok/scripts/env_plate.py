"""Shim — implementation in media.env_plate (hard-compat).

Keeps `import env_plate` working after package move.
"""
from __future__ import annotations

import sys as _sys

from media import env_plate as _impl

_sys.modules[__name__] = _impl

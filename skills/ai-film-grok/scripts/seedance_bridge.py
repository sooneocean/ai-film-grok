"""Shim — implementation in media.seedance_bridge (hard-compat).

Keeps `import seedance_bridge` working after package move.
"""
from __future__ import annotations

from media import seedance_bridge as _impl
import sys as _sys

_sys.modules[__name__] = _impl

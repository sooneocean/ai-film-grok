"""Shim — implementation in media.seedance_bridge (hard-compat).

Keeps `import seedance_bridge` working after package move.
"""
from __future__ import annotations

import sys as _sys

from media import seedance_bridge as _impl

_sys.modules[__name__] = _impl

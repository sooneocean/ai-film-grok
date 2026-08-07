"""Shim — implementation in plan.creative_workshop (hard-compat).

Keeps `import creative_workshop` working after package move.
"""
from __future__ import annotations

import sys as _sys

from plan import creative_workshop as _impl

_sys.modules[__name__] = _impl

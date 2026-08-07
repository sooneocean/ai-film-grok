"""Shim — implementation in plan.creative_quality (hard-compat).

Keeps `import creative_quality` working after package move.
"""
from __future__ import annotations

import sys as _sys

from plan import creative_quality as _impl

_sys.modules[__name__] = _impl

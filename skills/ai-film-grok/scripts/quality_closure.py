"""Shim — implementation in plan.quality_closure (hard-compat).

Keeps `import quality_closure` working after package move.
"""
from __future__ import annotations

import sys as _sys

from plan import quality_closure as _impl

_sys.modules[__name__] = _impl

"""Shim — implementation in plan.benchmark (hard-compat).

Keeps `import benchmark` working after package move.
"""
from __future__ import annotations

import sys as _sys

from plan import benchmark as _impl

_sys.modules[__name__] = _impl

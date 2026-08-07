"""Shim — implementation in plan.optimization_experiments (hard-compat).

Keeps `import optimization_experiments` working after package move.
"""
from __future__ import annotations

import sys as _sys

from plan import optimization_experiments as _impl

_sys.modules[__name__] = _impl

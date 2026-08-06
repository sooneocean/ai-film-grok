"""Shim — implementation in plan.mix_partial (hard-compat).

Keeps `import mix_partial` working after package move.
"""
from __future__ import annotations

from plan import mix_partial as _impl
import sys as _sys

_sys.modules[__name__] = _impl

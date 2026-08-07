"""Shim — implementation in plan.mix_partial (hard-compat).

Keeps `import mix_partial` working after package move.
"""
from __future__ import annotations

import sys as _sys

from plan import mix_partial as _impl

_sys.modules[__name__] = _impl

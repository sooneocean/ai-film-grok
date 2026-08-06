"""Shim — implementation in plan.creative_pipeline (hard-compat).

Keeps `import creative_pipeline` working after package move.
"""
from __future__ import annotations

from plan import creative_pipeline as _impl
import sys as _sys

_sys.modules[__name__] = _impl

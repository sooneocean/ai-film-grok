"""Shim — implementation in plan.creative_pipeline (hard-compat).

Keeps `import creative_pipeline` working after package move.
"""
from __future__ import annotations

import sys as _sys

from plan import creative_pipeline as _impl

_sys.modules[__name__] = _impl

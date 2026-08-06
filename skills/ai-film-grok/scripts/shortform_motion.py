"""Shim — implementation in plan.shortform_motion (hard-compat).

Keeps `import shortform_motion` working after package move.
"""
from __future__ import annotations

from plan import shortform_motion as _impl
import sys as _sys

_sys.modules[__name__] = _impl

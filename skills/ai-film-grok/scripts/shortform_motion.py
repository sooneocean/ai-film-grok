"""Shim — implementation in plan.shortform_motion (hard-compat).

Keeps `import shortform_motion` working after package move.
"""
from __future__ import annotations

import sys as _sys

from plan import shortform_motion as _impl

_sys.modules[__name__] = _impl

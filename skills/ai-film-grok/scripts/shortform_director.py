"""Shim — implementation in plan.shortform_director (hard-compat).

Keeps `import shortform_director` working after package move.
"""
from __future__ import annotations

from plan import shortform_director as _impl
import sys as _sys

_sys.modules[__name__] = _impl

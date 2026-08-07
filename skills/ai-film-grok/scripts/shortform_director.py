"""Shim — implementation in plan.shortform_director (hard-compat).

Keeps `import shortform_director` working after package move.
"""
from __future__ import annotations

import sys as _sys

from plan import shortform_director as _impl

_sys.modules[__name__] = _impl

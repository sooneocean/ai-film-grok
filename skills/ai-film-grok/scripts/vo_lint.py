"""Shim — implementation in narrative.vo_lint (hard-compat).

Keeps `import vo_lint` working after package move.
"""
from __future__ import annotations

from narrative import vo_lint as _impl
import sys as _sys

_sys.modules[__name__] = _impl

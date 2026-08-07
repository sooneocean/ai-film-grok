"""Shim — implementation in narrative.vo_lint (hard-compat).

Keeps `import vo_lint` working after package move.
"""
from __future__ import annotations

import sys as _sys

from narrative import vo_lint as _impl

_sys.modules[__name__] = _impl

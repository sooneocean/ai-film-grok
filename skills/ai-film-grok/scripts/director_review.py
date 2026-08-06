"""Shim — implementation in plan.director_review (hard-compat).

Keeps `import director_review` working after package move.
"""
from __future__ import annotations

from plan import director_review as _impl
import sys as _sys

_sys.modules[__name__] = _impl

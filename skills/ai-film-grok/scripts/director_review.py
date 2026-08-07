"""Shim — implementation in plan.director_review (hard-compat).

Keeps `import director_review` working after package move.
"""
from __future__ import annotations

import sys as _sys

from plan import director_review as _impl

_sys.modules[__name__] = _impl

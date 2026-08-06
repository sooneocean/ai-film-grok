"""Shim — implementation in plan.film_spec_profile (hard-compat).

Keeps `import film_spec_profile` working after package move.
"""
from __future__ import annotations

from plan import film_spec_profile as _impl
import sys as _sys

_sys.modules[__name__] = _impl

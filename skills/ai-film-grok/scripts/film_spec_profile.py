"""Shim — implementation in plan.film_spec_profile (hard-compat).

Keeps `import film_spec_profile` working after package move.
"""
from __future__ import annotations

import sys as _sys

from plan import film_spec_profile as _impl

_sys.modules[__name__] = _impl

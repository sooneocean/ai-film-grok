"""Shim — implementation in util.runtime_policy (hard-compat).

Keeps `import runtime_policy` working after package move.
"""
from __future__ import annotations

import sys as _sys

from util import runtime_policy as _impl

_sys.modules[__name__] = _impl

"""Shim — implementation in util.security_policy (hard-compat).

Keeps `import security_policy` working after package move.
"""
from __future__ import annotations

from util import security_policy as _impl
import sys as _sys

_sys.modules[__name__] = _impl

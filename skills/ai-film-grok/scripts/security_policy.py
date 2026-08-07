"""Shim — implementation in util.security_policy (hard-compat).

Keeps `import security_policy` working after package move.
"""
from __future__ import annotations

import sys as _sys

from util import security_policy as _impl

_sys.modules[__name__] = _impl

"""Shim — implementation in spine.automation_verify (hard-compat).

Keeps `import automation_verify` working after package move.
"""
from __future__ import annotations

import sys as _sys

from spine import automation_verify as _impl

_sys.modules[__name__] = _impl

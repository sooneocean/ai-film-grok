"""Shim — implementation in spine.automation_verify (hard-compat).

Keeps `import automation_verify` working after package move.
"""
from __future__ import annotations

from spine import automation_verify as _impl
import sys as _sys

_sys.modules[__name__] = _impl

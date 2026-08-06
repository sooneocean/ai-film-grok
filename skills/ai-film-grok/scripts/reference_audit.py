"""Shim — implementation in media.reference_audit (hard-compat).

Keeps `import reference_audit` working after package move.
"""
from __future__ import annotations

from media import reference_audit as _impl
import sys as _sys

_sys.modules[__name__] = _impl

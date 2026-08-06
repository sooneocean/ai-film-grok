"""Shim — implementation in media.performance_evidence (hard-compat).

Keeps `import performance_evidence` working after package move.
"""
from __future__ import annotations

from media import performance_evidence as _impl
import sys as _sys

_sys.modules[__name__] = _impl

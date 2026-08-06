"""Shim — implementation in gates.quality_evidence (hard-compat).

Keeps `import quality_evidence` working after package move.
"""
from __future__ import annotations

from gates import quality_evidence as _impl
import sys as _sys

_sys.modules[__name__] = _impl

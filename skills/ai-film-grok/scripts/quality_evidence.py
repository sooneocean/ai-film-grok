"""Shim — implementation in gates.quality_evidence (hard-compat).

Keeps `import quality_evidence` working after package move.
"""
from __future__ import annotations

import sys as _sys

from gates import quality_evidence as _impl

_sys.modules[__name__] = _impl

"""Shim — implementation in media.performance_evidence (hard-compat).

Keeps `import performance_evidence` working after package move.
"""
from __future__ import annotations

import sys as _sys

from media import performance_evidence as _impl

_sys.modules[__name__] = _impl

"""Shim — implementation in media.interactive_orchestration (hard-compat).

Keeps `import interactive_orchestration` working after package move.
"""
from __future__ import annotations

from media import interactive_orchestration as _impl
import sys as _sys

_sys.modules[__name__] = _impl

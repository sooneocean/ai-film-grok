"""Shim — implementation in gates.framing_lint (hard-compat).

Keeps `import framing_lint` working after package move.
"""
from __future__ import annotations

from gates import framing_lint as _impl
import sys as _sys

_sys.modules[__name__] = _impl

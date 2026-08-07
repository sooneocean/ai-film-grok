"""Shim — implementation in gates.native_text_gate (hard-compat).

Keeps `import native_text_gate` working after package move.
"""
from __future__ import annotations

import sys as _sys

from gates import native_text_gate as _impl

_sys.modules[__name__] = _impl

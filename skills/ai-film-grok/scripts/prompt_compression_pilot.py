"""Shim — implementation in plan.prompt_compression_pilot (hard-compat).

Keeps `import prompt_compression_pilot` working after package move.
"""
from __future__ import annotations

from plan import prompt_compression_pilot as _impl
import sys as _sys

_sys.modules[__name__] = _impl

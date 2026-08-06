"""Shim — implementation in plan.local_llm (hard-compat).

Keeps `import local_llm` working after package move.
"""
from __future__ import annotations

from plan import local_llm as _impl
import sys as _sys

_sys.modules[__name__] = _impl

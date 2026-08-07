"""Shim — implementation in plan.local_llm (hard-compat).

Keeps `import local_llm` working after package move.
"""
from __future__ import annotations

import sys as _sys

from plan import local_llm as _impl

_sys.modules[__name__] = _impl

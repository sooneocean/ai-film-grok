"""Shim — implementation in plan.prompt_budget (hard-compat).

Keeps `import prompt_budget` working after package move.
"""
from __future__ import annotations

from plan import prompt_budget as _impl
import sys as _sys

_sys.modules[__name__] = _impl

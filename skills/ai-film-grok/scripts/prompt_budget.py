"""Shim — implementation in plan.prompt_budget (hard-compat).

Keeps `import prompt_budget` working after package move.
"""
from __future__ import annotations

import sys as _sys

from plan import prompt_budget as _impl

_sys.modules[__name__] = _impl

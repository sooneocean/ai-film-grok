"""Shim — implementation in plan.motion_prompt_spine (hard-compat).

Keeps `import motion_prompt_spine` working after package move.
"""
from __future__ import annotations

from plan import motion_prompt_spine as _impl
import sys as _sys

_sys.modules[__name__] = _impl

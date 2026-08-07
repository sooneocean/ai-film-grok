"""Shim — implementation in plan.motion_prompt_spine (hard-compat).

Keeps `import motion_prompt_spine` working after package move.
"""
from __future__ import annotations

import sys as _sys

from plan import motion_prompt_spine as _impl

_sys.modules[__name__] = _impl

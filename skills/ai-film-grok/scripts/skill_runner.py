"""Shim — implementation in spine.skill_runner (hard-compat).

Keeps `import skill_runner` working after package move.
"""
from __future__ import annotations

from spine import skill_runner as _impl
import sys as _sys

_sys.modules[__name__] = _impl

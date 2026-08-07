"""Shim — implementation in spine.skill_runner (hard-compat).

Keeps `import skill_runner` working after package move.
"""
from __future__ import annotations

import sys as _sys

from spine import skill_runner as _impl

_sys.modules[__name__] = _impl

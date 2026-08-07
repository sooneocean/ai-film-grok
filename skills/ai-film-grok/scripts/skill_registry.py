"""Shim — implementation in spine.skill_registry (hard-compat).

Keeps `import skill_registry` working after package move.
"""
from __future__ import annotations

import sys as _sys

from spine import skill_registry as _impl

_sys.modules[__name__] = _impl

"""Shim — implementation in plan.prompt_injector (hard-compat).

Keeps `import prompt_injector` working after package move.
"""
from __future__ import annotations

from plan import prompt_injector as _impl
import sys as _sys

_sys.modules[__name__] = _impl

"""Shim — implementation in plan.prompt_injector (hard-compat).

Keeps `import prompt_injector` working after package move.
"""
from __future__ import annotations

import sys as _sys

from plan import prompt_injector as _impl

_sys.modules[__name__] = _impl

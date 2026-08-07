"""Shim — implementation in plan.prompt_compression_pilot (hard-compat).

Keeps `import prompt_compression_pilot` working after package move.
"""
from __future__ import annotations

import sys as _sys

from plan import prompt_compression_pilot as _impl

_sys.modules[__name__] = _impl

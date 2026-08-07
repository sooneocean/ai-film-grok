"""Shim — implementation in plan.serial_quality (hard-compat).

Keeps `import serial_quality` working after package move.
"""
from __future__ import annotations

import sys as _sys

from plan import serial_quality as _impl

_sys.modules[__name__] = _impl

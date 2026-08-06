"""Shim — implementation in plan.serial_quality (hard-compat).

Keeps `import serial_quality` working after package move.
"""
from __future__ import annotations

from plan import serial_quality as _impl
import sys as _sys

_sys.modules[__name__] = _impl

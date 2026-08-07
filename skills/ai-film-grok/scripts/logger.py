"""Shim — implementation in util.structured_logger (hard-compat).

Keeps `import logger` working after package move (distinct from util.logger).
"""
from __future__ import annotations

from util import structured_logger as _impl
import sys as _sys

_sys.modules[__name__] = _impl

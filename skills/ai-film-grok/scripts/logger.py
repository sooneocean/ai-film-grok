"""Shim — implementation in util.structured_logger (hard-compat).

Keeps `import logger` working after package move (distinct from util.logger).
"""
from __future__ import annotations

import sys as _sys

from util import structured_logger as _impl

_sys.modules[__name__] = _impl

"""Shim — implementation in util.config_loader (hard-compat).

Keeps `import config_loader` working after package move.
"""
from __future__ import annotations

import sys as _sys

from util import config_loader as _impl

_sys.modules[__name__] = _impl

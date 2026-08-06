"""Shim — implementation in media.h3_timeline_prompt (hard-compat).

Keeps `import h3_timeline_prompt` working after package move.
"""
from __future__ import annotations

from media import h3_timeline_prompt as _impl
import sys as _sys

_sys.modules[__name__] = _impl

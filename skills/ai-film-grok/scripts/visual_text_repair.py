"""Shim — implementation in media.visual_text_repair (hard-compat).

Keeps `import visual_text_repair` working after package move.
"""
from __future__ import annotations

import sys as _sys

from media import visual_text_repair as _impl

_sys.modules[__name__] = _impl

"""Shim — implementation in media.visual_text_audit (hard-compat).

Keeps `import visual_text_audit` working after package move.
"""
from __future__ import annotations

import sys as _sys

from media import visual_text_audit as _impl

_sys.modules[__name__] = _impl

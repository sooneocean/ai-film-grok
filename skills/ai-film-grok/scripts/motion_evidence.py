"""Shim — implementation in media.motion_evidence (hard-compat).

Keeps `import motion_evidence` working after package move.
"""
from __future__ import annotations

import sys as _sys

from media import motion_evidence as _impl

_sys.modules[__name__] = _impl

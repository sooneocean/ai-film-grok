"""Shim — implementation in post.transition_frame_audit (hard-compat).

Keeps `import transition_frame_audit` working after package move.
"""
from __future__ import annotations

from post import transition_frame_audit as _impl
import sys as _sys

_sys.modules[__name__] = _impl

"""Shim — implementation in post.transition_frame_audit (hard-compat).

Keeps `import transition_frame_audit` working after package move.
"""
from __future__ import annotations

import sys as _sys

from post import transition_frame_audit as _impl

_sys.modules[__name__] = _impl

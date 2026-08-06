"""Shim — implementation in media.i2v_motion_gate (W6 package layout).

Keeps `import i2v_motion_gate` / `from i2v_motion_gate import …` working for hard-compat.
"""
import sys as _sys

from media import i2v_motion_gate as _impl

_sys.modules[__name__] = _impl

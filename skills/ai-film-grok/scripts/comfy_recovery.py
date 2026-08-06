"""Shim — implementation in media.comfy_recovery (W6 package layout).

Keeps `import comfy_recovery` / `from comfy_recovery import …` working for hard-compat.
"""
import sys as _sys

from media import comfy_recovery as _impl

_sys.modules[__name__] = _impl

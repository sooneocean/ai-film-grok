"""Shim — implementation in media.comfy_recovery (W6 package layout).

Keeps `import comfy_recovery` / `from comfy_recovery import …` working for hard-compat.
"""
from media import comfy_recovery as _impl
import sys as _sys

_sys.modules[__name__] = _impl

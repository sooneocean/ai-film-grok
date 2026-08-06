"""Shim — implementation in media.comfy_armory (W6 package layout).

Keeps `import comfy_armory` / `from comfy_armory import …` working for hard-compat.
"""
import sys as _sys

from media import comfy_armory as _impl

_sys.modules[__name__] = _impl

"""Shim — implementation in media.comfy_armory (W6 package layout).

Keeps `import comfy_armory` / `from comfy_armory import …` working for hard-compat.
"""
from media import comfy_armory as _impl
import sys as _sys

_sys.modules[__name__] = _impl

"""Shim — implementation in narrative.dialogue_scene_package (W7 package layout).

Keeps `import dialogue_scene_package` / `from dialogue_scene_package import …` working for hard-compat.
"""
from narrative import dialogue_scene_package as _impl
import sys as _sys

_sys.modules[__name__] = _impl

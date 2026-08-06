"""Shim — implementation in narrative.dialogue_scene_package (W7 package layout).

Keeps `import dialogue_scene_package` / `from dialogue_scene_package import …` working for hard-compat.
"""
import sys as _sys

from narrative import dialogue_scene_package as _impl

_sys.modules[__name__] = _impl

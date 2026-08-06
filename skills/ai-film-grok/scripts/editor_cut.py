"""Shim — implementation in narrative.editor_cut (W7 package layout).

Keeps `import editor_cut` / `from editor_cut import …` working for hard-compat.
"""
from narrative import editor_cut as _impl
import sys as _sys

_sys.modules[__name__] = _impl

"""Shim — implementation in narrative.edit_edl_merge (W7 package layout).

Keeps `import edit_edl_merge` / `from edit_edl_merge import …` working for hard-compat.
"""
import sys as _sys

from narrative import edit_edl_merge as _impl

_sys.modules[__name__] = _impl

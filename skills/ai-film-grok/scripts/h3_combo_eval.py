"""Shim — implementation in media.h3_combo_eval (W6 package layout).

Keeps `import h3_combo_eval` / `from h3_combo_eval import …` working for hard-compat.
"""
import sys as _sys

from media import h3_combo_eval as _impl

_sys.modules[__name__] = _impl

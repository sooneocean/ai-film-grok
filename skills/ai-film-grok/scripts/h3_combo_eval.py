"""Shim — implementation in media.h3_combo_eval (W6 package layout).

Keeps `import h3_combo_eval` / `from h3_combo_eval import …` working for hard-compat.
"""
from media import h3_combo_eval as _impl
import sys as _sys

_sys.modules[__name__] = _impl

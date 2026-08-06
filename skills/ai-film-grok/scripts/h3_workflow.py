"""Shim — implementation in media.h3_workflow (W6 package layout).

Keeps `import h3_workflow` / `from h3_workflow import …` working for hard-compat.
"""
import sys as _sys

from media import h3_workflow as _impl

_sys.modules[__name__] = _impl

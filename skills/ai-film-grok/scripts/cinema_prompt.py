"""Shim — implementation in narrative.cinema_prompt (W7 package layout).

Keeps `import cinema_prompt` / `from cinema_prompt import …` working for hard-compat.
"""
import sys as _sys

from narrative import cinema_prompt as _impl

_sys.modules[__name__] = _impl

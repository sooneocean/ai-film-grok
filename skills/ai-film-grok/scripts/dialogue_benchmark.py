"""Shim — implementation in narrative.dialogue_benchmark (W7 package layout).

Keeps `import dialogue_benchmark` / `from dialogue_benchmark import …` working for hard-compat.
"""
import sys as _sys

from narrative import dialogue_benchmark as _impl

_sys.modules[__name__] = _impl

"""Shim — implementation in narrative.dialogue_benchmark_queue (W7 package layout).

Keeps `import dialogue_benchmark_queue` / `from dialogue_benchmark_queue import …` working for hard-compat.
"""
import sys as _sys

from narrative import dialogue_benchmark_queue as _impl

_sys.modules[__name__] = _impl

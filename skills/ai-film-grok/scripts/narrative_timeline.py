"""Shim — implementation in plan.narrative_timeline (W7 package layout).

Keeps `import narrative_timeline` / `from narrative_timeline import …` working for hard-compat.
"""
import sys as _sys

from plan import narrative_timeline as _impl

_sys.modules[__name__] = _impl

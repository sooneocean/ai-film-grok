"""Shim — implementation in plan.narrative_evidence (W7 package layout).

Keeps `import narrative_evidence` / `from narrative_evidence import …` working for hard-compat.
"""
import sys as _sys

from plan import narrative_evidence as _impl

_sys.modules[__name__] = _impl

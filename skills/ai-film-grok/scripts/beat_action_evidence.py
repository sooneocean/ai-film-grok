"""Shim — implementation in plan.beat_action_evidence (W3 package layout).

Keeps `import beat_action_evidence` / `from beat_action_evidence import …` working for hard-compat.
"""

from __future__ import annotations

from plan import beat_action_evidence as _impl
import sys as _sys

_sys.modules[__name__] = _impl

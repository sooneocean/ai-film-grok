"""Shim — implementation in spine.next_actions (W3 package layout).

Keeps `import next_actions` / `from next_actions import …` working for hard-compat.
"""

from __future__ import annotations

from spine import next_actions as _impl
import sys as _sys

_sys.modules[__name__] = _impl

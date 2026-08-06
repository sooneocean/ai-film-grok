"""Shim — implementation in spine.next_actions (W3 package layout).

Keeps `import next_actions` / `from next_actions import …` working for hard-compat.
"""

from __future__ import annotations

import sys as _sys

from spine import next_actions as _impl

_sys.modules[__name__] = _impl

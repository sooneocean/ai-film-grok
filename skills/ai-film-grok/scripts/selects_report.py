"""Shim — implementation in spine.selects_report (W3 package layout).

Keeps `import selects_report` / `from selects_report import …` working for hard-compat.
"""

from __future__ import annotations

from spine import selects_report as _impl
import sys as _sys

_sys.modules[__name__] = _impl

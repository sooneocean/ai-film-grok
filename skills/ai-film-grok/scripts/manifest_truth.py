"""Shim — implementation in gates.manifest_truth (W3 package layout).

Keeps `import manifest_truth` / `from manifest_truth import …` working for hard-compat.
"""

from __future__ import annotations

import sys as _sys

from gates import manifest_truth as _impl

_sys.modules[__name__] = _impl

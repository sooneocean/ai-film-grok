"""Shim — implementation in assets.face_identity (W3 package layout).

Keeps `import face_identity` / `from face_identity import …` working for hard-compat.
"""

from __future__ import annotations

from assets import face_identity as _impl
import sys as _sys

_sys.modules[__name__] = _impl

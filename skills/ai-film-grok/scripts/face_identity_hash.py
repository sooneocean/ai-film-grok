"""Shim — implementation in assets.face_identity_hash (W3 package layout).

Keeps `import face_identity_hash` / `from face_identity_hash import …` working for hard-compat.
"""

from __future__ import annotations

from assets import face_identity_hash as _impl
import sys as _sys

_sys.modules[__name__] = _impl

"""Shim — implementation in assets.face_identity_hash (W3 package layout).

Keeps `import face_identity_hash` / `from face_identity_hash import …` working for hard-compat.
"""

from __future__ import annotations

import sys as _sys

from assets import face_identity_hash as _impl

_sys.modules[__name__] = _impl

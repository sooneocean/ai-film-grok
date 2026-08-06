"""Shim — implementation in assets.face_identity (W3 package layout).

Keeps `import face_identity` / `from face_identity import …` working for hard-compat.
"""

from __future__ import annotations

import sys as _sys

from assets import face_identity as _impl

_sys.modules[__name__] = _impl

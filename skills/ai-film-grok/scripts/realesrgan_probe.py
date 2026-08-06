"""Shim — implementation in media.realesrgan_probe (hard-compat).

Keeps ``import realesrgan_probe`` / probe_command paths working after W6 media move.
"""

from __future__ import annotations

import sys as _sys

from media import realesrgan_probe as _impl

_sys.modules[__name__] = _impl

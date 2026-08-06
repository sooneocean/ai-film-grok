"""Shim — implementation in media.comfy_broker_service (W6 package layout).

Keeps `import comfy_broker_service` / `from comfy_broker_service import …` working for hard-compat.
"""
import sys as _sys

from media import comfy_broker_service as _impl

_sys.modules[__name__] = _impl

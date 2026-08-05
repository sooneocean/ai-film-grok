"""Shim — implementation in media.comfy_broker_service (W6 package layout).

Keeps `import comfy_broker_service` / `from comfy_broker_service import …` working for hard-compat.
"""
from media import comfy_broker_service as _impl
import sys as _sys

_sys.modules[__name__] = _impl

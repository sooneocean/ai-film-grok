"""Shim — implementation in web.web_core."""
import sys as _sys

from web import web_core as _impl

_sys.modules[__name__] = _impl

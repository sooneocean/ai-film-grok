"""Shim — implementation in web.web_api."""
import sys as _sys

from web import web_api as _impl

_sys.modules[__name__] = _impl

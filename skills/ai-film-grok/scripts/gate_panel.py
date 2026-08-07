"""Shim — implementation in web.gate_panel."""
import sys as _sys

from web import gate_panel as _impl

_sys.modules[__name__] = _impl

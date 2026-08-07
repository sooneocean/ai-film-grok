"""Shim — implementation in narrative.edit_transition (T5 peel).

Keeps `import edit_transition` / `from edit_transition import …` working.
"""
import sys as _sys

from narrative import edit_transition as _impl

_sys.modules[__name__] = _impl

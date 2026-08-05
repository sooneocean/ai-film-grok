"""Shim — implementation in plan.film_spec (W7 package layout).

Keeps `import film_spec` / `from film_spec import …` working for hard-compat.
"""
from plan import film_spec as _impl
import sys as _sys

_sys.modules[__name__] = _impl

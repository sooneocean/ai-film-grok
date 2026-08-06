"""Shim — implementation in post.render_final (W4).

When imported, re-exports the package module for hard-compat.
When executed as a script (``python render_final.py`` / aifilm final plate),
must call ``main()`` — otherwise the process exits 0 in ~1s with no work
(lesson 2026-08-06 suse-evolution-ep01).
"""
from post import render_final as _impl
import sys as _sys

if __name__ == "__main__":
    raise SystemExit(_impl.main())

_sys.modules[__name__] = _impl

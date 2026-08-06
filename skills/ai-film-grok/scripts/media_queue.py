"""Shim — implementation in media.media_queue (W6 package layout).

Keeps ``import media_queue`` / ``from media_queue import …`` working for hard-compat.
When executed as a script, dispatch to ``media.media_queue.main()`` (same pattern as
``render_final.py`` — bare shim exit 0 with no work is a production footgun).
"""
import sys as _sys

from media import media_queue as _impl

if __name__ == "__main__":
    raise SystemExit(_impl.main())

_sys.modules[__name__] = _impl

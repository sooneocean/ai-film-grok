"""Shim — implementation in media.cloud_media_download (W6 package layout).

Keeps `import cloud_media_download` / `from cloud_media_download import …` working for hard-compat.
"""
import sys as _sys

from media import cloud_media_download as _impl

_sys.modules[__name__] = _impl

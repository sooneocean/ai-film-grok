"""Shim — implementation in media.cloud_media_download (W6 package layout).

Keeps `import cloud_media_download` / `from cloud_media_download import …` working for hard-compat.
"""
from media import cloud_media_download as _impl
import sys as _sys

_sys.modules[__name__] = _impl

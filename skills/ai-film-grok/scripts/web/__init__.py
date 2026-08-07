"""Localhost workbench package: static console + route contract + state projection.

Hard-compat shims:
  import web_routes          → web.routes
  import console_projection  → web.projection
"""

from __future__ import annotations

__all__ = ["routes", "projection"]

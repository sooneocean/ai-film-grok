#!/usr/bin/env python3
"""Shim — implementation in web.smoke_console."""
from __future__ import annotations

from web.smoke_console import *  # noqa: F403
from web.smoke_console import main  # noqa: F401

if __name__ == "__main__":
    raise SystemExit(main())

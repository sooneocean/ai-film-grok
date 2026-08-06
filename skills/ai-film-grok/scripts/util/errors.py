"""Shared error types for the ai-film-grok pipeline.

This module is dependency-free (no imports from aifilm_grok) so it can be
imported by util/* without creating a circular dependency. ``aifilm_grok.py``
re-exports ``FilmError`` from here for backward compatibility.
"""

from __future__ import annotations

from typing import Any


class FilmError(RuntimeError):
    """User-facing workflow error."""

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.details = details or {}

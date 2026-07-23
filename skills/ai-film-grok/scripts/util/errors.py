"""Shared error types for the ai-film-grok pipeline.

This module is dependency-free (no imports from aifilm_grok) so it can be
imported by util/* without creating a circular dependency. ``aifilm_grok.py``
re-exports ``FilmError`` from here for backward compatibility.
"""

from __future__ import annotations


class FilmError(RuntimeError):
    """User-facing workflow error."""

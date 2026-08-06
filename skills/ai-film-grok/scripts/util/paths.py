"""Portable path resolution — remove macOS-only hardcoded paths.

The codebase previously hardcoded ``/Users/dex/...`` and ``/opt/homebrew/bin``
in several subprocess/env sites. That makes the plugin run *only* on one Apple
Silicon Mac and breaks Linux/CI reproducibility. These helpers keep the current
macOS behavior byte-identical while making the paths discoverable on any
platform.

Design rules (P3-2):
- Never inject a path that does not exist on the current machine.
- The plugin root is derived from ``__file__`` (repo-relative), never a user dir.
- Subprocess ``PATH`` always includes the standard system bindirs.
"""
from __future__ import annotations

from pathlib import Path

# util/paths.py lives at <plugin>/skills/ai-film-grok/scripts/util/paths.py
# parents[4] walks back to the plugin root (<plugin>/ai-film-grok).
_PLUGIN_ROOT = Path(__file__).resolve().parents[4]


def plugin_root() -> Path:
    """Absolute plugin root of this checkout (portable, no hardcoded user dir)."""
    return _PLUGIN_ROOT


def homebrew_bin() -> str:
    """Homebrew ``bin`` directory for the current platform, or '' if absent.

    Apple-Silicon macOS installs to ``/opt/homebrew/bin``; Intel macOS and
    Linux use ``/usr/local/bin`` or ``/home/linuxbrew/.linuxbrew/bin``.
    Returns '' when none exist so callers never inject a non-existent path.
    """
    for candidate in (
        "/opt/homebrew/bin",
        "/home/linuxbrew/.linuxbrew/bin",
        "/usr/local/bin",
    ):
        if Path(candidate).is_dir():
            return candidate
    return ""


def build_subprocess_path() -> str:
    """A portable ``PATH`` for subprocess environments.

    Prepends the homebrew/linuxbrew bin dir only when it actually exists;
    always includes the standard system bindirs so Linux/CI is reproducible.
    """
    parts = [homebrew_bin(), "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"]
    return ":".join(part for part in parts if part)


def first_existing_file(*candidates: Path) -> Path | None:
    """Return the first candidate that resolves to an existing file, else None."""
    for candidate in candidates:
        try:
            resolved = candidate.resolve(strict=True)
        except OSError:
            continue
        if resolved.is_file():
            return resolved
    return None

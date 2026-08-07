"""Framework-agnostic security primitives for the localhost review console.

These helpers are shared by the stdlib review UI (``review_ui.py``) and the
future FastAPI gateway so the transport / auth / media rules stay identical
regardless of which web framework serves the page.  No third-party dependency:
only the stdlib plus the repo's own ``util`` module.
"""

from __future__ import annotations

import hashlib
import secrets
from pathlib import Path
from typing import Any

from util import (
    exclusive_file_lock,
    read_json,
    sha256_file,
    utc_now,
    write_json,
)

MAX_BODY = 128 * 1024
MEDIA_SUFFIXES = frozenset(
    {
        ".mp4",
        ".mov",
        ".m4v",
        ".webm",
        ".wav",
        ".mp3",
        ".m4a",
        ".png",
        ".jpg",
        ".jpeg",
        ".webp",
    }
)


class WebConsoleError(ValueError):
    """A UI request violates the review-console contract."""


class WebConsoleConflict(WebConsoleError):
    """The browser acted on an outdated revision."""


class WebConsoleForbidden(Exception):
    """A hard gate failed: the action is rejected by server-side policy (403).

    Distinct from :class:`WebConsoleError` so gateways map it to HTTP 403
    (not 400) and so an ``except WebConsoleError`` clause does not swallow it.
    """


def generate_token() -> str:
    """Return a URL-safe 32-byte random token for loopback session auth."""
    return secrets.token_urlsafe(32)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def token_matches(provided: str | None, expected: str | None) -> bool:
    """Constant-time comparison so token timing leaks nothing."""
    return secrets.compare_digest(str(provided or ""), str(expected or ""))


def loopback_origin_ok(origin: str, port: int) -> bool:
    """Reject any cross-origin request that did not originate from this server."""
    return origin == f"http://127.0.0.1:{port}"


def safe_media_path(root: Path | str, relative: str) -> Path:
    """Resolve a media path inside the workspace.

    Rejects symlinks, path escapes, and any non-media suffix.  Mirrors the
    escape protection already proven in ``review_ui._safe_media``.
    """
    base = Path(root).resolve()
    candidate = (base / relative).resolve()
    if (
        not candidate.is_file()
        or candidate.is_symlink()
        or candidate.suffix.lower() not in MEDIA_SUFFIXES
        or base not in candidate.parents
    ):
        raise WebConsoleError("media path is outside the film workspace")
    return candidate


def read_json_safe(path: Path | str) -> Any:
    return read_json(Path(path))


def write_json_locked(path: Path | str, data: dict[str, Any]) -> None:
    """Atomically write JSON under an exclusive lock; never world-readable."""
    path = Path(path)
    with exclusive_file_lock(path):
        write_json(path, data)
        path.chmod(0o600)


def workspace_binding_sha256(root: Path | str, *relpaths: str) -> str:
    """Hash the current bytes of the given workspace files into one binding.

    Selections are bound to this digest: if any upstream file changes, a
    stored selection becomes stale and must be re-confirmed.
    """
    base = Path(root).resolve()
    hasher = hashlib.sha256()
    for relative in relpaths:
        target = (base / relative).resolve()
        if target.is_file() and base in target.parents and not target.is_symlink():
            hasher.update(sha256_file(target).encode("utf-8"))
    return hasher.hexdigest()


def now_iso() -> str:
    return utc_now()

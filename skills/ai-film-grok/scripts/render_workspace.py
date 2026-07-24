"""Filesystem boundary for final rendering.

Keeping path validation and workspace preparation outside the renderer lets
timeline/audio/subtitle stages remain focused on media decisions.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from security_policy import (
    SecurityPolicyError,
    reject_symlinks,
    safe_output_path,
    safe_workspace_directory,
)


class RenderWorkspaceError(RuntimeError):
    pass


def resolve_render_paths(root: Path, out_name: str | None) -> dict[str, Path]:
    """Resolve all renderer-owned paths before any media command runs."""
    root = root.expanduser().resolve()
    if not root.is_dir():
        raise RenderWorkspaceError(f"Film root missing: {root}")
    try:
        out_dir = safe_workspace_directory(root, "out", field="film output directory")
        audio_dir = safe_workspace_directory(root, "audio", field="film audio directory")
        clips_dir = safe_workspace_directory(root, "clips", field="film clips directory")
        keyframes_dir = safe_workspace_directory(
            root, "keyframes", field="film keyframes directory"
        )
        native_dir = safe_workspace_directory(audio_dir, "native", field="native audio directory")
        work = safe_workspace_directory(out_dir, "_final_work", field="final work directory")
        final = safe_output_path(
            out_dir,
            out_name or "film_final.mp4",
            suffixes={".mp4"},
            field="final output name",
        )
    except SecurityPolicyError as exc:
        raise RenderWorkspaceError(str(exc)) from exc
    return {
        "root": root,
        "out_dir": out_dir,
        "final": final,
        "audio_dir": audio_dir,
        "clips_dir": clips_dir,
        "keyframes_dir": keyframes_dir,
        "native_dir": native_dir,
        "work": work,
    }


def prepare_render_workspace(paths: dict[str, Path]) -> None:
    """Reject unsafe directories and recreate only the renderer's work area."""
    try:
        for key, field in (
            ("out_dir", "film output directory"),
            ("audio_dir", "film audio directory"),
            ("clips_dir", "film clips directory"),
            ("keyframes_dir", "film keyframes directory"),
            ("native_dir", "native audio directory"),
        ):
            reject_symlinks(paths[key], field=field)
    except SecurityPolicyError as exc:
        raise RenderWorkspaceError(str(exc)) from exc
    work = paths["work"]
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    paths["audio_dir"].mkdir(exist_ok=True)
    (work / "overlays").mkdir()

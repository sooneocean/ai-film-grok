from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from render_workspace import (  # noqa: E402
    RenderWorkspaceError,
    prepare_render_workspace,
    resolve_render_paths,
)


def test_workspace_resolves_and_recreates_only_final_work(tmp_path: Path) -> None:
    for name in ("out", "audio", "clips", "keyframes"):
        (tmp_path / name).mkdir()
    work = tmp_path / "out" / "_final_work"
    work.mkdir()
    (work / "old.txt").write_text("old")

    paths = resolve_render_paths(tmp_path, None)
    prepare_render_workspace(paths)

    assert paths["final"] == tmp_path / "out" / "film_final.mp4"
    assert not (work / "old.txt").exists()
    assert (work / "overlays").is_dir()


def test_workspace_rejects_output_path_escape(tmp_path: Path) -> None:
    for name in ("out", "audio", "clips", "keyframes"):
        (tmp_path / name).mkdir()

    with pytest.raises(RenderWorkspaceError, match="output name"):
        resolve_render_paths(tmp_path, "../escape.mp4")

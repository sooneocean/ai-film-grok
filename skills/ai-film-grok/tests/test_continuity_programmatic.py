"""Continuity programmatic MVP (v2.40)."""

from __future__ import annotations

import json
from pathlib import Path

from continuity_programmatic import check_continuity_programmatic


def _write_spec(root: Path, shots: list[dict], *, longform: bool = True) -> None:
    spec = {
        "title": "t",
        "production_mode": "longform" if longform else "shortform",
        "long_form": longform,
        "scenes": [{"id": "s1", "shots": shots}],
    }
    (root / "film-spec.json").write_text(json.dumps(spec), encoding="utf-8")


def test_continue_forbidden_transition(tmp_path: Path):
    _write_spec(
        tmp_path,
        [
            {"id": "a", "chain_mode": "hard"},
            {
                "id": "b",
                "chain_mode": "continue",
                "transition": "dissolve",
                "duration_sec": 5,
            },
        ],
    )
    (tmp_path / "continuity_chain.md").write_text("# chain\njoin a→b continue\n", encoding="utf-8")
    rep = check_continuity_programmatic(tmp_path, write=False)
    codes = {i["code"] for i in rep["issues"]}
    assert "CONTINUE_FORBIDDEN_TRANSITION" in codes
    assert rep["ok"] is False


def test_shortform_no_doc_ok(tmp_path: Path):
    _write_spec(tmp_path, [{"id": "a", "duration_sec": 5}], longform=False)
    rep = check_continuity_programmatic(tmp_path, write=False)
    assert rep["ok"] is True


def test_frame_hash_mismatch(tmp_path: Path):
    _write_spec(
        tmp_path,
        [
            {"id": "a", "chain_mode": "hard"},
            {"id": "b", "chain_mode": "continue"},
        ],
    )
    (tmp_path / "continuity_chain.md").write_text("# chain\njoin continue\n", encoding="utf-8")
    kf = tmp_path / "keyframes"
    kf.mkdir()
    (kf / "a_last.jpg").write_bytes(b"frame-a")
    (kf / "b.jpg").write_bytes(b"frame-b-different")
    rep = check_continuity_programmatic(tmp_path, write=False)
    codes = {i["code"] for i in rep["issues"]}
    assert "CONTINUE_FRAME_HASH_MISMATCH" in codes

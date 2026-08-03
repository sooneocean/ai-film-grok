from __future__ import annotations

import json
import sys
from argparse import Namespace
from pathlib import Path

import jsonschema
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from project_state import (  # noqa: E402
    assert_audio_mutation_safe,
    build_project_state,
    persist_project_state,
)


def test_project_state_is_deterministic_and_persisted_separately(tmp_path: Path) -> None:
    (tmp_path / "film-spec.json").write_text(
        json.dumps(
            {
                "title": "State",
                "production_mode": "shortform",
                "scenes": [],
            }
        ),
        encoding="utf-8",
    )
    gates = {"graph_valid": True, "style_locked": False}
    actions = [{"id": "lock-style", "cmd": "aifilm lock-style"}]

    first = build_project_state(
        tmp_path,
        gates=gates,
        next_actions=actions,
        next_id="lock-style",
        next_cmd="aifilm lock-style",
    )
    second = build_project_state(
        tmp_path,
        gates=gates,
        next_actions=actions,
        next_id="lock-style",
        next_cmd="aifilm lock-style",
    )

    assert first == second
    assert first["state_sha256"] == second["state_sha256"]
    assert not (tmp_path / "receipts" / "project-state.json").exists()
    path = persist_project_state(tmp_path, first)
    persisted = json.loads(path.read_text())
    assert persisted["state_sha256"] == first["state_sha256"]
    schema = json.loads(
        (
            Path(__file__).resolve().parents[1] / "schemas" / "project-state-snapshot.schema.json"
        ).read_text()
    )
    jsonschema.Draft202012Validator(schema).validate(persisted)


def test_status_projects_canonical_state_without_writing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import aifilm_grok
    from cli_status import cmd_status

    (tmp_path / "film-spec.json").write_text(
        json.dumps(
            {
                "title": "Read only",
                "production_mode": "shortform",
                "scenes": [],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            aifilm_grok.empty_manifest(
                title="Read only",
                theme="status",
                aspect="9:16",
            )
        ),
        encoding="utf-8",
    )
    before = {
        path.relative_to(tmp_path): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }
    captured: list[dict[str, object]] = []
    monkeypatch.setattr(aifilm_grok, "emit", captured.append)

    assert cmd_status(Namespace(root=str(tmp_path), no_write=True)) == 0

    after = {
        path.relative_to(tmp_path): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }
    assert after == before
    assert captured[0]["canonical_stage"] == captured[0]["project_state"]["canonical_stage"]
    assert captured[0]["phase"]["id"] == "define_story"
    assert captured[0]["phase"]["total"] == 7


def test_project_state_surfaces_final_before_master_conflict(tmp_path: Path) -> None:
    (tmp_path / "film-spec.json").write_text('{"production_mode":"shortform"}', encoding="utf-8")
    state = build_project_state(
        tmp_path,
        gates={"final_complete": True, "desktop_exported": True},
        next_actions=[],
        next_id="x",
        next_cmd="x",
    )
    assert "FINAL_BEFORE_CANONICAL_MASTER" in state["blockers"]
    assert state["truth_conflicts"]


def test_audio_mutation_is_blocked_by_truth_conflict(tmp_path: Path) -> None:
    (tmp_path / "film-spec.json").write_text('{"production_mode":"shortform"}', encoding="utf-8")
    (tmp_path / "manifest.json").write_text(
        json.dumps({"gates": {"final_complete": True}}), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="FINAL_BEFORE_CANONICAL_MASTER"):
        assert_audio_mutation_safe(tmp_path)

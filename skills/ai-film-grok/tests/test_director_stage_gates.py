from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from approval_ledger import (
    append_approval,  # noqa: E402
    read_approval_ledger,  # noqa: E402
)
from director_cli import (  # noqa: E402
    lock_native_stage,
    native_stage_input_refs,
    validate_native_stage_evidence,
)
from director_stage_gates import (  # noqa: E402
    STAGE_ORDER,
    lock_stage,
    stage_status,
)
from production_book import init_production_book  # noqa: E402


def _approve(root: Path, stage: str, hashes: dict[str, str], *, approver_type: str = "human"):
    return append_approval(
        root,
        scope=f"stage:{stage}",
        approval_type="stage_lock",
        approver_type=approver_type,
        approver="director",
        authorization_event=f"review:{stage}",
        input_hashes=hashes,
        evidence_refs=[f"review/{stage}.json"],
        transaction_id=f"tx-{stage}",
    )


def test_professional_stage_order_and_current_human_approval_are_hard(
    tmp_path: Path, monkeypatch
) -> None:
    init_production_book(tmp_path, rigor="professional")
    monkeypatch.setattr(
        "director_cli.validate_native_stage_evidence",
        lambda _root, _stage: {},
    )
    concept = tmp_path / "concept.md"
    concept.write_text("locked concept", encoding="utf-8")
    script = tmp_path / "script.md"
    script.write_text("draft one", encoding="utf-8")

    blocked = stage_status(tmp_path, target_stage="script_lock")
    assert not blocked["ok"]
    assert blocked["blocking"][0]["stage"] == "concept_lock"

    concept_hashes = {"concept": __import__("hashlib").sha256(concept.read_bytes()).hexdigest()}
    concept_approval = _approve(tmp_path, "concept_lock", concept_hashes)
    lock_stage(
        tmp_path,
        stage="concept_lock",
        input_refs={"concept": "concept.md"},
        approval_id=concept_approval["approval_id"],
    )
    script_hashes = {"script.md": __import__("hashlib").sha256(script.read_bytes()).hexdigest()}
    script_approval = _approve(tmp_path, "script_lock", script_hashes)
    lock_stage(
        tmp_path,
        stage="script_lock",
        input_refs={"script.md": "script.md"},
        approval_id=script_approval["approval_id"],
    )

    assert stage_status(tmp_path, target_stage="script_lock")["ok"]
    script.write_text("draft two", encoding="utf-8")
    stale = stage_status(tmp_path, target_stage="script_lock")
    assert not stale["ok"]
    assert any(issue["code"] == "STAGE_INPUT_STALE" for issue in stale["blocking"])


def test_guided_art_locks_are_advisory_but_integrity_locks_block(tmp_path: Path) -> None:
    init_production_book(tmp_path, rigor="guided")

    art = stage_status(tmp_path, target_stage="department_look_lock")
    assert art["ok"]
    assert {item["stage"] for item in art["warnings"]} == {
        "concept_lock",
        "script_lock",
        "department_look_lock",
    }

    integrity = stage_status(tmp_path, target_stage="picture_lock")
    assert not integrity["ok"]
    assert any(item["stage"] == "dailies_review" for item in integrity["blocking"])


def test_legacy_reports_warnings_and_stage_order_is_canonical(tmp_path: Path) -> None:
    init_production_book(tmp_path, rigor="legacy")

    report = stage_status(tmp_path, target_stage="master_lock")

    assert report["ok"]
    assert not report["blocking"]
    assert len(report["warnings"]) == len(STAGE_ORDER)


def test_professional_lock_rejects_arbitrary_file_without_native_stage_evidence(
    tmp_path: Path,
) -> None:
    init_production_book(tmp_path, rigor="professional")
    arbitrary = tmp_path / "looks-valid.json"
    arbitrary.write_text('{"approved":true}\n', encoding="utf-8")
    digest = __import__("hashlib").sha256(arbitrary.read_bytes()).hexdigest()
    approval = _approve(tmp_path, "concept_lock", {"arbitrary": digest})

    with pytest.raises(ValueError, match="native evidence missing"):
        lock_stage(
            tmp_path,
            stage="concept_lock",
            input_refs={"arbitrary": "looks-valid.json"},
            approval_id=approval["approval_id"],
        )


def test_failed_native_stage_validation_does_not_leave_orphan_approval(
    tmp_path: Path,
) -> None:
    init_production_book(tmp_path, rigor="professional")

    with pytest.raises(ValueError, match="native evidence missing"):
        lock_native_stage(
            tmp_path,
            stage="concept_lock",
            approver="dex",
            user_phrase="批准",
        )

    assert read_approval_ledger(tmp_path)["approvals"] == []


def test_team_gate_blocks_stage_lock_before_approval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import director_cli
    import production_team

    (tmp_path / "production-team.json").write_text("{}\n", encoding="utf-8")
    receipts = tmp_path / "receipts"
    receipts.mkdir()
    (receipts / "capability-snapshot.json").write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(
        director_cli, "validate_native_stage_evidence", lambda *_args: {"brief": "brief.json"}
    )
    monkeypatch.setattr(
        production_team,
        "validate_team",
        lambda *_args, **_kwargs: {"ok": False, "blockers": ["NO_MODEL_ASSIGNED:showrunner"]},
    )

    with pytest.raises(ValueError, match="production-team stage gate"):
        lock_native_stage(
            tmp_path,
            stage="concept_lock",
            approver="dex",
            user_phrase="批准",
        )

    assert read_approval_ledger(tmp_path)["approvals"] == []


def test_bulk_native_refs_bind_each_approved_clip_file(tmp_path: Path) -> None:
    clip = tmp_path / "clips" / "s001.mp4"
    clip.parent.mkdir(parents=True)
    clip.write_bytes(b"clip")
    digest = __import__("hashlib").sha256(clip.read_bytes()).hexdigest()
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "clips": {
                    "s001": {
                        "status": "approved",
                        "path": "clips/s001.mp4",
                        "sha256": digest,
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    refs = native_stage_input_refs(tmp_path, "bulk")

    assert refs["media:s001:0"] == "clips/s001.mp4"


def test_custom_refs_cannot_detach_lock_from_native_stage_evidence(tmp_path: Path) -> None:
    init_production_book(tmp_path, rigor="professional")
    (tmp_path / "brief.json").write_text('{"title":"t"}\n', encoding="utf-8")
    story = tmp_path / "drama-graph.json"
    story.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "story": {
                    "premise": "p",
                    "logline": "l",
                    "protagonist_goal": "g",
                    "opposition": "o",
                    "stakes": "s",
                    "climax_choice": "c",
                    "ending_hook": "e",
                    "emotional_arc": ["a", "b", "c"],
                },
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "marker.txt").write_text("marker\n", encoding="utf-8")

    report = lock_native_stage(
        tmp_path,
        stage="concept_lock",
        approver="dex",
        user_phrase="批准",
        input_refs={"marker": "marker.txt"},
    )
    assert {"brief", "story", "marker"} <= set(report["input_refs"])

    story.write_text('{"schema_version":2}\n', encoding="utf-8")

    assert stage_status(tmp_path, target_stage="concept_lock")["ok"] is False


def test_bulk_validation_accepts_canonical_nested_scene_shots(tmp_path: Path) -> None:
    clip = tmp_path / "clips" / "s001.mp4"
    clip.parent.mkdir(parents=True)
    clip.write_bytes(b"clip")
    digest = __import__("hashlib").sha256(clip.read_bytes()).hexdigest()
    (tmp_path / "film-spec.json").write_text(
        json.dumps({"scenes": [{"shots": [{"id": "s001"}]}]}),
        encoding="utf-8",
    )
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "clips": {
                    "s001": {
                        "status": "approved",
                        "path": "clips/s001.mp4",
                        "sha256": digest,
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    refs = validate_native_stage_evidence(tmp_path, "bulk")

    assert refs["media:s001:0"] == "clips/s001.mp4"


def test_concept_lock_rejects_noncanonical_drama_graph(tmp_path: Path) -> None:
    (tmp_path / "brief.json").write_text('{"title":"t"}\n', encoding="utf-8")
    (tmp_path / "drama-graph.json").write_text(
        '{"schema_version":1}\n',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="canonical semantic drama graph"):
        validate_native_stage_evidence(tmp_path, "concept_lock")


def test_department_lock_requires_locked_visual_bible(tmp_path: Path) -> None:
    (tmp_path / "style-bible.json").write_text(
        '{"locked":false}\n',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="locked visual bible"):
        validate_native_stage_evidence(tmp_path, "department_look_lock")


def test_shot_animatic_lock_requires_matching_ids_and_durations(tmp_path: Path) -> None:
    (tmp_path / "drama-graph.json").write_text('{"schema_version":2}\n', encoding="utf-8")
    (tmp_path / "film-spec.json").write_text(
        json.dumps({"scenes": [{"shots": [{"id": "s001", "duration_sec": 4}]}]}),
        encoding="utf-8",
    )
    (tmp_path / "timeline.json").write_text(
        json.dumps({"shots": [{"id": "s002", "duration_sec": 4}]}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="ordered shot ids"):
        validate_native_stage_evidence(tmp_path, "shot_animatic_lock")


def test_shot_animatic_lock_fails_closed_on_missing_dramatic_meaning(
    tmp_path: Path,
) -> None:
    (tmp_path / "drama-graph.json").write_text('{"schema_version":2}\n', encoding="utf-8")
    spec = {
        "dramatic_meaning_strict": True,
        "scenes": [{"shots": [{"id": "s001", "duration_sec": 4}]}],
    }
    (tmp_path / "film-spec.json").write_text(json.dumps(spec), encoding="utf-8")
    (tmp_path / "timeline.json").write_text(
        json.dumps({"shots": [{"id": "s001", "duration_sec": 4}]}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="dramatic meaning"):
        validate_native_stage_evidence(tmp_path, "shot_animatic_lock")


def test_shot_animatic_lock_accepts_meaningful_shot(tmp_path: Path) -> None:
    (tmp_path / "drama-graph.json").write_text('{"schema_version":2}\n', encoding="utf-8")
    spec = {
        "dramatic_meaning_strict": True,
        "scenes": [
            {
                "shots": [
                    {
                        "id": "s001",
                        "duration_sec": 4,
                        "dramatic_function": "action",
                        "dsl": {"visible_change": "door swings open"},
                    }
                ]
            }
        ],
    }
    (tmp_path / "film-spec.json").write_text(json.dumps(spec), encoding="utf-8")
    (tmp_path / "timeline.json").write_text(
        json.dumps({"shots": [{"id": "s001", "duration_sec": 4}]}),
        encoding="utf-8",
    )

    refs = validate_native_stage_evidence(tmp_path, "shot_animatic_lock")
    assert refs

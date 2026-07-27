from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from creative_workshop import (  # noqa: E402
    WorkshopConflict,
    WorkshopLocked,
    apply_workshop,
    compile_workshop,
    diagnose_workshop,
    export_workshop,
    intake_workshop,
    validate_workshop,
)
from story_plan import project_graph_to_film_spec  # noqa: E402


def _graph() -> dict:
    return {
        "episodes": [
            {
                "id": "ep01",
                "scenes": [
                    {
                        "id": "sc01",
                        "beats": [
                            {
                                "id": "bt01",
                                "shots": [
                                    {
                                        "id": "shot01",
                                        "duration_sec": 6,
                                        "narrativePurpose": "evidence reveal",
                                        "characterIds": ["hero"],
                                        "locationId": "station",
                                        "dsl": {
                                            "subject": "a woman in a red coat",
                                            "action": "turns toward the arriving train",
                                            "camera": {"shot_size": "medium close-up"},
                                            "lighting": "cold platform light from camera left",
                                        },
                                        "dialogue": "别回头。",
                                        "performance": {"intent": "restrained warning"},
                                        "end_state": "she keeps the ticket visible in her hand",
                                        "reference_assets": [
                                            {
                                                "asset_type": "character",
                                                "label": "heroine reference",
                                                "use_only": "face, short hair, red coat",
                                                "do_not_reference": "pose or background",
                                            },
                                            {
                                                "asset_type": "prop",
                                                "label": "ticket reference",
                                                "use_only": "one worn paper ticket",
                                                "do_not_reference": "duplicate tickets",
                                                "single_instance": True,
                                            },
                                        ],
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
        ]
    }


def _brief() -> dict:
    return {
        "platform": "douyin",
        "rhythm_profile": "short_video_medium_high",
        "audience": "vertical drama viewers",
        "target_duration_sec": 45,
        "genre": "mystery",
        "constraints": ["dialogue remains Chinese"],
    }


def test_intake_is_revision_bound_and_does_not_replace_without_revision(tmp_path: Path) -> None:
    first = intake_workshop(tmp_path, _brief(), expected_revision=0)
    assert first["revision"] == 1
    with pytest.raises(WorkshopConflict, match="expected revision"):
        intake_workshop(tmp_path, _brief(), expected_revision=0)
    second = intake_workshop(tmp_path, _brief(), expected_revision=1)
    assert second["revision"] == 2


def test_compile_validate_and_export_are_local_and_provider_neutral(tmp_path: Path) -> None:
    intake_workshop(tmp_path, _brief(), expected_revision=0)
    (tmp_path / "drama-graph.json").write_text(
        json.dumps(_graph(), ensure_ascii=False), encoding="utf-8"
    )

    diagnosis = diagnose_workshop(tmp_path)
    packet = compile_workshop(tmp_path)
    report = validate_workshop(tmp_path)
    exported = export_workshop(tmp_path, target="frw-seedance")

    assert diagnosis["source"]["kind"] == "drama-graph"
    assert packet["provider_policy"] == "provider_neutral"
    assert packet["shots"][0]["director_prompt"]["references"][0]["use_only"]
    assert report["ok"]
    assert exported["external_action"] is False
    assert exported["provider_default_changed"] is False
    assert "asset-" not in exported["prompts"][0]["text"]
    assert (tmp_path / "receipts" / "workshop" / "compile.json").is_file()
    assert (tmp_path / "receipts" / "workshop" / "export-frw-seedance.json").is_file()


def test_validate_catches_reference_role_limit_and_prompt_contamination(tmp_path: Path) -> None:
    intake_workshop(tmp_path, _brief(), expected_revision=0)
    graph = _graph()
    shot = graph["episodes"][0]["scenes"][0]["beats"][0]["shots"][0]
    shot["duration_sec"] = 16
    shot["reference_assets"] = [
        {"asset_type": "character", "label": f"ref {index}", "use_only": "face"}
        for index in range(10)
    ]
    shot["dsl"]["subject"] = "CH001 asset-hero"
    (tmp_path / "drama-graph.json").write_text(
        json.dumps(graph, ensure_ascii=False), encoding="utf-8"
    )

    compile_workshop(tmp_path)
    report = validate_workshop(tmp_path, strict=True)
    codes = {item["code"] for item in report["errors"]}
    assert {"UNIT_DURATION_EXCEEDED", "REFERENCE_IMAGE_LIMIT", "PROMPT_INTERNAL_ID"} <= codes


def test_validate_rejects_a_packet_when_its_story_source_changes(tmp_path: Path) -> None:
    intake_workshop(tmp_path, _brief(), expected_revision=0)
    (tmp_path / "drama-graph.json").write_text(json.dumps(_graph()), encoding="utf-8")
    compile_workshop(tmp_path)
    graph = _graph()
    graph["title"] = "changed after compile"
    (tmp_path / "drama-graph.json").write_text(json.dumps(graph), encoding="utf-8")

    report = validate_workshop(tmp_path)
    assert not report["ok"]
    assert report["errors"][0]["code"] == "WORKSHOP_SOURCE_STALE"
    with pytest.raises(ValueError, match="WORKSHOP_SOURCE_STALE"):
        export_workshop(tmp_path, target="grok")


def test_validate_and_export_reject_a_tampered_packet(tmp_path: Path) -> None:
    intake_workshop(tmp_path, _brief(), expected_revision=0)
    (tmp_path / "drama-graph.json").write_text(json.dumps(_graph()), encoding="utf-8")
    compile_workshop(tmp_path)
    packet_path = tmp_path / "receipts" / "workshop" / "compile.json"
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    packet["shots"][0]["director_prompt"]["subject"] = "tampered subject"
    packet_path.write_text(json.dumps(packet), encoding="utf-8")

    report = validate_workshop(tmp_path, strict=True)
    assert {item["code"] for item in report["errors"]} == {"WORKSHOP_PACKET_TAMPERED"}
    with pytest.raises(ValueError, match="WORKSHOP_PACKET_TAMPERED"):
        export_workshop(tmp_path, target="generic")


def test_validate_blocks_asset_underscore_internal_ids(tmp_path: Path) -> None:
    intake_workshop(tmp_path, _brief(), expected_revision=0)
    graph = _graph()
    graph["episodes"][0]["scenes"][0]["beats"][0]["shots"][0]["dsl"]["subject"] = (
        "asset_hero waits on the platform"
    )
    (tmp_path / "drama-graph.json").write_text(json.dumps(graph), encoding="utf-8")
    compile_workshop(tmp_path)

    report = validate_workshop(tmp_path, strict=True)
    assert "PROMPT_INTERNAL_ID" in {item["code"] for item in report["errors"]}
    with pytest.raises(ValueError, match="PROMPT_INTERNAL_ID"):
        export_workshop(tmp_path, target="grok")


def test_compile_accepts_canonical_graph_projection_fields_and_lints_dialogue_rate(
    tmp_path: Path,
) -> None:
    intake_workshop(tmp_path, _brief(), expected_revision=0)
    graph = _graph()
    shot = graph["episodes"][0]["scenes"][0]["beats"][0]["shots"][0]
    shot.pop("duration_sec")
    shot.pop("dialogue")
    shot["targetDuration"] = 3
    shot.pop("dsl")
    shot["_film"] = {
        "dsl": {
            "subject": "woman in a red coat",
            "action": "turns toward the train",
            "camera": {"shot_size": "medium"},
            "lighting": "cold platform light",
        },
        "nar": "这是一个会超过每秒六个中文字符的台词速度检查句子。",
    }
    (tmp_path / "drama-graph.json").write_text(json.dumps(graph), encoding="utf-8")

    packet = compile_workshop(tmp_path)
    report = validate_workshop(tmp_path, strict=True)
    assert packet["shots"][0]["duration_sec"] == 3
    assert packet["shots"][0]["director_prompt"]["subject"] == "woman in a red coat"
    assert "DIALOGUE_RATE_HIGH" in {item["code"] for item in report["errors"]}


def test_apply_is_revision_bound_and_projects_creative_fields_to_unlocked_shots(
    tmp_path: Path,
) -> None:
    intake_workshop(tmp_path, _brief(), expected_revision=0)
    (tmp_path / "drama-graph.json").write_text(json.dumps(_graph()), encoding="utf-8")
    compile_workshop(tmp_path)

    applied = apply_workshop(tmp_path, expected_graph_revision=1)
    graph = json.loads((tmp_path / "drama-graph.json").read_text(encoding="utf-8"))
    shot = graph["episodes"][0]["scenes"][0]["beats"][0]["shots"][0]

    assert applied["graph_revision_before"] == 1
    assert applied["graph_revision_after"] == 2
    assert shot["creative"]["shot_function"] == "evidence reveal"
    assert shot["creative"]["reference_assets"][0]["label"] == "heroine reference"
    assert (tmp_path / "receipts" / "narrative" / "revision-0002.json").is_file()
    film_spec = project_graph_to_film_spec(graph)
    assert film_spec["scenes"][0]["shots"][0]["creative"] == shot["creative"]
    with pytest.raises(WorkshopConflict, match="expected graph revision"):
        apply_workshop(tmp_path, expected_graph_revision=1)


def test_apply_refuses_locked_shot_scope_and_empty_packets(tmp_path: Path) -> None:
    intake_workshop(tmp_path, _brief(), expected_revision=0)
    graph = _graph()
    graph["lock_scopes"] = ["shots"]
    (tmp_path / "drama-graph.json").write_text(json.dumps(graph), encoding="utf-8")
    compile_workshop(tmp_path)
    with pytest.raises(WorkshopLocked, match="shots scope is locked"):
        apply_workshop(tmp_path, expected_graph_revision=1)

    empty_root = tmp_path / "empty"
    empty_root.mkdir()
    intake_workshop(empty_root, _brief(), expected_revision=0)
    (empty_root / "drama-graph.json").write_text(json.dumps({"episodes": []}), encoding="utf-8")
    compile_workshop(empty_root)
    report = validate_workshop(empty_root, strict=True)
    assert "WORKSHOP_SHOTS_EMPTY" in {item["code"] for item in report["errors"]}


def test_diagnose_covers_the_remaining_dialogue_dimensions(tmp_path: Path) -> None:
    brief = {**_brief(), "genre": "historical"}
    intake_workshop(tmp_path, brief, expected_revision=0)
    graph = _graph()
    shot = graph["episodes"][0]["scenes"][0]["beats"][0]["shots"][0]
    shot["dialogue"] = "OK，正如你所知，项目今晚必须完成。"
    shot.pop("subtext", None)
    (tmp_path / "drama-graph.json").write_text(json.dumps(graph), encoding="utf-8")

    report = diagnose_workshop(tmp_path)
    codes = {item["code"] for item in report["findings"]}
    assert {"SUBTEXT_MISSING", "EXPOSITION_RISK", "GENRE_VOICE_DRIFT"} <= codes


def test_cli_e2e_writes_only_local_contracts(tmp_path: Path) -> None:
    brief_path = tmp_path / "brief-input.json"
    brief_path.write_text(json.dumps(_brief()), encoding="utf-8")
    (tmp_path / "drama-graph.json").write_text(json.dumps(_graph()), encoding="utf-8")
    cli = SCRIPTS / "aifilm"

    for arguments in (
        ("intake", "--file", str(brief_path), "--expected-revision", "0"),
        ("diagnose",),
        ("compile",),
        ("validate", "--strict"),
        ("apply", "--expected-graph-revision", "1"),
        ("compile",),
        ("validate", "--strict"),
        ("export", "--target", "grok"),
    ):
        proc = subprocess.run(
            [str(cli), "workshop", *arguments, "--root", str(tmp_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == 0, proc.stderr
        assert json.loads(proc.stdout)["content_sha256"]

    export = json.loads((tmp_path / "receipts" / "workshop" / "export-grok.json").read_text())
    assert export["external_action"] is False
    assert export["provider_default_changed"] is False

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

from scene_sound import reconcile


def _write_spec(
    root: Path,
    event: dict | None = None,
    *,
    top_level: bool = False,
    audio_cues: list[dict] | None = None,
) -> None:
    shot = {"id": "s1", "action": "她走到门边，扭动门把，推门进入。"}
    if audio_cues:
        shot["audio_cues"] = audio_cues
    spec = {"shots": [shot]} if top_level else {"scenes": [{"shots": [shot]}]}
    if event:
        spec["sound_plan"] = {"scene_events": [event]}
    (root / "film-spec.json").write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")


def test_reconcile_infers_required_actions_and_blocks_missing_assets(tmp_path: Path):
    _write_spec(tmp_path)
    report = reconcile(tmp_path)
    assert report["status"] == "blocked"
    assert {item["kind"] for item in report["events"]} >= {
        "ambience",
        "footsteps",
        "door_handle",
        "door_open",
    }
    assert (tmp_path / "receipts" / "scene-sound-status.json").is_file()


def _asset_event(tmp_path: Path, *, kind: str = "door_open") -> dict:
    asset = tmp_path / "audio" / "door.wav"
    asset.parent.mkdir(exist_ok=True)
    asset.write_bytes(b"door sound")
    return {
        "shot_id": "s1",
        "kind": kind,
        "source": "local:audio/door.wav",
        "source_sha256": sha256(asset.read_bytes()).hexdigest(),
        "license": "test-local",
        "start_offset_sec": 0,
        "duration_sec": 0.1,
    }


def test_legacy_scene_event_is_not_proof_of_rendered_sound(tmp_path: Path):
    _write_spec(tmp_path, _asset_event(tmp_path))
    report = reconcile(tmp_path, write=False)
    door = next(item for item in report["events"] if item["kind"] == "door_open")
    assert door["status"] == "blocked"
    assert door["source"] == "inferred"


def test_missing_or_unhashed_local_asset_does_not_clear_required_event(tmp_path: Path):
    _write_spec(tmp_path, {"shot_id": "s1", "kind": "door_open", "source": "local:missing.wav"})
    report = reconcile(tmp_path, write=False)
    door = next(item for item in report["events"] if item["kind"] == "door_open")
    assert door["status"] == "blocked"


def test_top_level_shots_are_reconciled(tmp_path: Path):
    _write_spec(tmp_path, top_level=True)
    report = reconcile(tmp_path, write=False)
    assert report["status"] == "blocked"
    assert report["summary"]["required"] == 4


def test_verified_audio_cue_with_unknown_material_requires_review(tmp_path: Path):
    cue = _asset_event(tmp_path, kind="foley")
    cue.pop("shot_id")
    cue["asset_hint"] = "door_open"
    _write_spec(tmp_path, audio_cues=[cue])
    report = reconcile(tmp_path, write=False)
    door = next(item for item in report["events"] if item["kind"] == "door_open")
    assert door["status"] == "needs_review"
    assert door["needs_review"] is True
    assert door["source"] == "audio_cues"


def test_summary_counts_blocked_events_not_unique_shots(tmp_path: Path):
    _write_spec(tmp_path, top_level=True)
    report = reconcile(tmp_path, write=False)
    assert report["summary"]["required"] == 4
    assert report["summary"]["blocked"] == 4
    assert report["summary"]["ok"] == 0


def test_narrative_silence_explicitly_exempts_ambience(tmp_path: Path):
    _write_spec(tmp_path, top_level=True)
    spec_path = tmp_path / "film-spec.json"
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    spec["shots"][0]["scene_silent"] = True
    spec_path.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    report = reconcile(tmp_path, write=False)
    assert "ambience" not in {item["kind"] for item in report["events"]}


def test_english_door_verb_and_string_false_do_not_hide_required_sound(tmp_path: Path):
    spec = {
        "shots": [
            {
                "id": "s1",
                "visible_change": "She opens the door and enters.",
                "scene_silent": "false",
            }
        ]
    }
    (tmp_path / "film-spec.json").write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    report = reconcile(tmp_path, write=False)
    assert {item["kind"] for item in report["events"]} == {"ambience", "door_open"}


def test_known_foley_material_must_match_the_shot(tmp_path: Path):
    cue = _asset_event(tmp_path, kind="foley")
    cue.pop("shot_id")
    cue.update({"asset_hint": "footsteps", "material": "tile"})
    _write_spec(tmp_path, top_level=True, audio_cues=[cue])
    spec_path = tmp_path / "film-spec.json"
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    spec["shots"][0]["floor_material"] = "wood"
    spec_path.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    report = reconcile(tmp_path, write=False)
    footsteps = next(item for item in report["events"] if item["kind"] == "footsteps")
    assert footsteps["status"] == "blocked"
    assert footsteps["expected_material"] == "wood"
    assert footsteps["actual_material"] == "tile"


def test_matching_material_wins_over_an_earlier_mismatched_candidate(tmp_path: Path):
    wrong = _asset_event(tmp_path, kind="foley")
    right = _asset_event(tmp_path, kind="foley")
    for cue, material in ((wrong, "tile"), (right, "wood")):
        cue.pop("shot_id")
        cue.update({"asset_hint": "footsteps", "material": material})
    _write_spec(tmp_path, top_level=True, audio_cues=[wrong, right])
    spec_path = tmp_path / "film-spec.json"
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    spec["shots"][0]["floor_material"] = "wood"
    spec_path.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    report = reconcile(tmp_path, write=False)
    footsteps = next(item for item in report["events"] if item["kind"] == "footsteps")
    assert footsteps["status"] == "ok"
    assert footsteps["actual_material"] == "wood"


def test_unknown_material_requires_review_even_with_a_verified_local_asset(tmp_path: Path):
    cue = _asset_event(tmp_path, kind="foley")
    cue.pop("shot_id")
    cue.update({"asset_hint": "footsteps", "material": "neutral"})
    _write_spec(tmp_path, top_level=True, audio_cues=[cue])
    report = reconcile(tmp_path, write=False)
    footsteps = next(item for item in report["events"] if item["kind"] == "footsteps")
    assert footsteps["status"] == "needs_review"
    assert footsteps["needs_review"] is True
    assert report["status"] == "blocked"  # ambience and door events still need assets


def test_muted_or_unrenderable_cues_do_not_clear_required_sound(tmp_path: Path):
    cue = _asset_event(tmp_path, kind="ambience")
    cue.pop("shot_id")
    cue["muted"] = True
    spec = {"shots": [{"id": "s1", "duration_sec": 1, "audio_cues": [cue]}]}
    (tmp_path / "film-spec.json").write_text(json.dumps(spec), encoding="utf-8")

    report = reconcile(tmp_path, write=False)

    ambience = next(item for item in report["events"] if item["kind"] == "ambience")
    assert ambience["status"] == "blocked"


def test_cue_without_timeline_license_does_not_clear_required_sound(tmp_path: Path):
    cue = _asset_event(tmp_path, kind="ambience")
    cue.pop("shot_id")
    cue.pop("license")
    spec = {"shots": [{"id": "s1", "duration_sec": 1, "audio_cues": [cue]}]}
    (tmp_path / "film-spec.json").write_text(json.dumps(spec), encoding="utf-8")

    report = reconcile(tmp_path, write=False)

    ambience = next(item for item in report["events"] if item["kind"] == "ambience")
    assert ambience["status"] == "blocked"


def test_cue_without_explicit_timeline_position_does_not_clear_required_sound(tmp_path: Path):
    cue = _asset_event(tmp_path, kind="ambience")
    cue.pop("shot_id")
    cue.pop("start_offset_sec")
    spec = {"shots": [{"id": "s1", "duration_sec": 1, "audio_cues": [cue]}]}
    (tmp_path / "film-spec.json").write_text(json.dumps(spec), encoding="utf-8")

    report = reconcile(tmp_path, write=False)

    ambience = next(item for item in report["events"] if item["kind"] == "ambience")
    assert ambience["status"] == "blocked"

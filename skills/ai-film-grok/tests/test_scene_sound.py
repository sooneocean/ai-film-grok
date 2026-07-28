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
    assert {item["kind"] for item in report["events"]} >= {"footsteps", "door_handle", "door_open"}
    assert (tmp_path / "receipts" / "scene-sound-status.json").is_file()


def _asset_event(tmp_path: Path, *, kind: str = "door_open") -> dict:
    asset = tmp_path / "audio" / "door.wav"
    asset.parent.mkdir()
    asset.write_bytes(b"door sound")
    return {
        "shot_id": "s1",
        "kind": kind,
        "source": "local:audio/door.wav",
        "source_sha256": sha256(asset.read_bytes()).hexdigest(),
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
    assert report["summary"]["required"] == 3


def test_verified_audio_cue_satisfies_matching_required_event(tmp_path: Path):
    cue = _asset_event(tmp_path, kind="foley")
    cue.pop("shot_id")
    cue["asset_hint"] = "door_open"
    _write_spec(tmp_path, audio_cues=[cue])
    report = reconcile(tmp_path, write=False)
    door = next(item for item in report["events"] if item["kind"] == "door_open")
    assert door["status"] == "ok"
    assert door["source"] == "audio_cues"


def test_summary_counts_blocked_events_not_unique_shots(tmp_path: Path):
    _write_spec(tmp_path, top_level=True)
    report = reconcile(tmp_path, write=False)
    assert report["summary"]["required"] == 3
    assert report["summary"]["blocked"] == 3
    assert report["summary"]["ok"] == 0

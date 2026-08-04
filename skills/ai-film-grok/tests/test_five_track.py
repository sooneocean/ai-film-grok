"""Wave δ · 5-Track cinema mix policy + LUFS band."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from five_track import (  # noqa: E402
    LUFS_MAX_DEFAULT,
    LUFS_MIN_DEFAULT,
    LUFS_TARGET,
    FiveTrackError,
    audit_five_track,
    default_audio_tracks_block,
    ensure_five_track_defaults,
    five_track_enabled,
    lufs_band_for_spec,
    plan_five_track,
)


def test_dialogue_drama_enables_five_track() -> None:
    assert five_track_enabled({"vo_mode": "dialogue_drama"}) is True
    assert five_track_enabled({"heat_scale": "max"}) is True
    assert five_track_enabled({"quality_target": "premium_vertical"}) is True
    assert five_track_enabled({"five_track": False}) is False
    assert five_track_enabled({}) is False


def test_lufs_band_cinema() -> None:
    band = lufs_band_for_spec({"vo_mode": "dialogue_drama"})
    assert band["enabled"] is True
    assert band["strict"] is True
    assert band["lufs_min"] == LUFS_MIN_DEFAULT
    assert band["lufs_max"] == LUFS_MAX_DEFAULT
    assert band["target"] == LUFS_TARGET


def test_ensure_writes_audio_tracks() -> None:
    spec: dict = {"vo_mode": "dialogue_drama", "heat_scale": "max"}
    rep = ensure_five_track_defaults(spec)
    assert rep["enabled"] is True
    assert "audio_tracks" in (spec.get("sound_plan") or {})
    tracks = spec["sound_plan"]["audio_tracks"]
    for key in ("dx", "fx", "bg", "mx", "dialogue", "music"):
        assert key in tracks
    assert spec.get("lufs_strict") is True
    assert float(spec["lufs_min"]) == pytest.approx(LUFS_MIN_DEFAULT)
    assert float(spec["lufs_max"]) == pytest.approx(LUFS_MAX_DEFAULT)


def test_default_tracks_block_has_aliases() -> None:
    block = default_audio_tracks_block({"sound_plan": {"mood": "rnb"}})
    assert block["mx"]["mood"] == "rnb"
    assert block["sub"]["required"] is False


def test_plan_sex_sfx_missing(tmp_path: Path) -> None:
    spec = {
        "vo_mode": "dialogue_drama",
        "heat_scale": "max",
        "sound_plan": {"events": []},
        "scenes": [
            {
                "shots": [
                    {
                        "id": "m1",
                        "heat_phase": "act",
                        "duration_sec": 6,
                        "dramatic_function": "action",
                        "dsl": {
                            "motion": "thrust continuous",
                            "action": "hip thrust",
                            "visible_change": "hips move",
                        },
                    }
                ]
            }
        ],
    }
    (tmp_path / "film-spec.json").write_text(json.dumps(spec), encoding="utf-8")
    rep = plan_five_track(tmp_path, write=True)
    assert rep["enabled"] is True
    assert rep["sex_sfx"]["ok"] is False
    assert "m1" in (rep["sex_sfx"].get("missing") or [])
    assert (tmp_path / "receipts" / "five-track-plan.json").is_file()


def test_plan_sex_sfx_covered(tmp_path: Path) -> None:
    spec = {
        "vo_mode": "dialogue_drama",
        "heat_scale": "max",
        "sound_plan": {
            "events": [
                {"type": "sfx_accent", "shot_id": "m1", "sex_sfx": True, "kind": "impact"}
            ]
        },
        "scenes": [
            {
                "shots": [
                    {
                        "id": "m1",
                        "heat_phase": "act",
                        "duration_sec": 6,
                        "dsl": {"motion": "thrust", "action": "thrust"},
                    }
                ]
            }
        ],
    }
    (tmp_path / "film-spec.json").write_text(json.dumps(spec), encoding="utf-8")
    rep = plan_five_track(tmp_path, write=False)
    assert rep["sex_sfx"]["ok"] is True
    assert rep["ok"] is True


def test_audit_raises_when_enabled_and_bad(tmp_path: Path) -> None:
    spec = {
        "vo_mode": "dialogue_drama",
        "heat_scale": "max",
        "sound_plan": {"events": []},
        "scenes": [
            {
                "shots": [
                    {"id": "m1", "heat_phase": "climax", "dsl": {"motion": "peak"}}
                ]
            }
        ],
    }
    (tmp_path / "film-spec.json").write_text(json.dumps(spec), encoding="utf-8")
    with pytest.raises(FiveTrackError):
        audit_five_track(tmp_path, write=False)

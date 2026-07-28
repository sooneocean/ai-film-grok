from __future__ import annotations

import json
from pathlib import Path

import pytest
from automation_verify import build_verification_report


def test_verify_requires_scene_sound_and_delivery_for_timeline_v1(tmp_path: Path):
    (tmp_path / "film-spec.json").write_text(
        json.dumps(
            {
                "audio_timeline_v1": True,
                "shots": [{"id": "s1", "action": "她推门进入。"}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    report = build_verification_report(tmp_path)
    assert report["ok"] is False
    assert {"scene_sound", "audio_delivery"} <= set(report["blocking_checks"])


def test_verify_accepts_ready_audio_delivery_without_optional_production_book(tmp_path: Path):
    (tmp_path / "film-spec.json").write_text(
        json.dumps({"audio_timeline_v1": True, "shots": []}), encoding="utf-8"
    )
    audio = tmp_path / "audio"
    audio.mkdir()
    (audio / "audio-delivery-report.json").write_text(
        json.dumps({"ok": True, "stale": False}), encoding="utf-8"
    )
    report = build_verification_report(tmp_path)
    assert report["ok"] is True
    assert report["blocking_checks"] == []


@pytest.mark.parametrize("shots", [None, {}])
def test_verify_rejects_missing_or_invalid_timeline_shots(tmp_path: Path, shots) -> None:
    spec = {"audio_timeline_v1": True}
    if shots is not None:
        spec["shots"] = shots
    (tmp_path / "film-spec.json").write_text(json.dumps(spec), encoding="utf-8")
    audio = tmp_path / "audio"
    audio.mkdir()
    (audio / "audio-delivery-report.json").write_text(
        json.dumps({"ok": True, "stale": False}), encoding="utf-8"
    )

    report = build_verification_report(tmp_path)

    assert report["ok"] is False
    assert "scene_sound" in report["blocking_checks"]

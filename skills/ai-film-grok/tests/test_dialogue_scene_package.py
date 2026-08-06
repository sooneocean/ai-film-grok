from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import dialogue_scene_package as package_module  # noqa: E402
from dialogue_scene_package import (  # noqa: E402
    build_dialogue_scene_package,
    validate_audio_evidence,
    validate_dialogue_scene_package,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _production_evidence(package: dict, audio: Path, lipsync: Path) -> None:
    line = package["scenes"][0]["lines"][0]
    line["audio"] = {
        "status": "measured",
        "duration_sec": 1.0,
        "sha256": _sha256(audio),
        "path": str(audio),
    }
    line["lipsync"] = {
        "status": "approved",
        "reviewer": "human-reviewer",
        "artifact_sha256": _sha256(lipsync),
        "artifact_path": str(lipsync),
    }


def _graph() -> dict:
    return {
        "dialogue_ledger": [
            {
                "line_id": "sc02_ln07",
                "scene_ref": "sc02",
                "shot_ref": "shot07",
                "speaker": "heroine",
                "spoken_ja": "行く。",
                "caption_text": "我要走了。",
                "emotion": "压抑后决绝",
                "subtext": "她已决定反击",
                "addressee": "partner",
                "actions": {"during": "按住门把，抬眼"},
                "screen_mode": "on_camera",
                "lipsync_required": True,
            }
        ]
    }


def _spec() -> dict:
    return {
        "scenes": [
            {
                "shots": [
                    {
                        "id": "shot07",
                        "dialogue_line_id": "sc02_ln07",
                        "performance_state_id": "heroine-sc02-door",
                        "screen_mode": "on_camera",
                    }
                ]
            }
        ]
    }


def test_scene_package_makes_line_id_the_shared_production_key() -> None:
    package = build_dialogue_scene_package(_graph(), _spec())
    line = package["scenes"][0]["lines"][0]
    assert line["line_id"] == "sc02_ln07"
    assert line["scene_state_id"] == "heroine-sc02-door"
    assert line["audio"]["status"] == "pending_tts"
    assert validate_dialogue_scene_package(package)["ok"]


def test_production_on_camera_requires_real_audio_and_human_lipsync_review(
    tmp_path: Path,
) -> None:
    package = build_dialogue_scene_package(_graph(), _spec())
    report = validate_dialogue_scene_package(package, production=True, root=tmp_path)
    assert {item["code"] for item in report["errors"]} == {
        "TTS_EVIDENCE_MISSING",
        "LIPSYNC_REVIEW_MISSING",
    }


def test_production_off_camera_dialogue_requires_real_audio_but_not_lipsync(
    tmp_path: Path,
) -> None:
    graph = _graph()
    graph["dialogue_ledger"][0]["screen_mode"] = "off_camera"
    package = build_dialogue_scene_package(graph, _spec())

    report = validate_dialogue_scene_package(package, production=True, root=tmp_path)

    assert {item["code"] for item in report["errors"]} == {"TTS_EVIDENCE_MISSING"}


def test_production_rejects_forged_audio_or_lipsync_evidence(tmp_path: Path) -> None:
    package = build_dialogue_scene_package(_graph(), _spec())
    line = package["scenes"][0]["lines"][0]
    line["audio"] = {
        "status": "measured",
        "duration_sec": -1,
        "sha256": "not-a-sha",
        "path": "/no/such/audio.wav",
    }
    line["lipsync"] = {"status": "approved"}

    report = validate_dialogue_scene_package(package, production=True, root=tmp_path)

    assert {item["code"] for item in report["errors"]} == {
        "TTS_EVIDENCE_MISSING",
        "LIPSYNC_REVIEW_MISSING",
    }


def test_production_rejects_external_symlink_and_non_media_evidence(tmp_path: Path) -> None:
    root = tmp_path / "film"
    root.mkdir()
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"not media")

    package = build_dialogue_scene_package(_graph(), _spec())
    _production_evidence(package, outside, outside)
    report = validate_dialogue_scene_package(package, production=True, root=root)
    assert {item["code"] for item in report["errors"]} == {
        "TTS_EVIDENCE_MISSING",
        "LIPSYNC_REVIEW_MISSING",
    }

    linked = root / "linked.wav"
    linked.symlink_to(outside)
    _production_evidence(package, linked, linked)
    report = validate_dialogue_scene_package(package, production=True, root=root)
    assert {item["code"] for item in report["errors"]} == {
        "TTS_EVIDENCE_MISSING",
        "LIPSYNC_REVIEW_MISSING",
    }

    fake_audio = root / "fake.wav"
    fake_video = root / "fake.mp4"
    fake_audio.write_bytes(b"plain text with a wav suffix")
    fake_video.write_bytes(b"plain text with an mp4 suffix")
    _production_evidence(package, fake_audio, fake_video)
    report = validate_dialogue_scene_package(package, production=True, root=root)
    assert {item["code"] for item in report["errors"]} == {
        "TTS_EVIDENCE_MISSING",
        "LIPSYNC_REVIEW_MISSING",
    }


def test_production_accepts_secure_media_and_detects_probe_time_swap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "film"
    root.mkdir()
    audio = root / "line.wav"
    video = root / "lipsync.mp4"
    audio.write_bytes(b"trusted-audio")
    video.write_bytes(b"trusted-video")
    package = build_dialogue_scene_package(_graph(), _spec())
    _production_evidence(package, audio, video)
    monkeypatch.setattr(package_module, "_probe_media_fd", lambda fd, expected: True)
    assert validate_dialogue_scene_package(package, production=True, root=root)["ok"]

    outside = tmp_path / "replacement.wav"
    outside.write_bytes(b"replacement")

    def swap_during_probe(fd: int, expected: str) -> bool:
        del fd
        if expected == "audio" and not audio.is_symlink():
            audio.unlink()
            audio.symlink_to(outside)
        return True

    monkeypatch.setattr(package_module, "_probe_media_fd", swap_during_probe)
    report = validate_dialogue_scene_package(package, production=True, root=root)
    assert "TTS_EVIDENCE_MISSING" in {item["code"] for item in report["errors"]}


def test_public_audio_evidence_helper_is_root_bound(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "film"
    root.mkdir()
    audio = root / "line.wav"
    audio.write_bytes(b"trusted-audio")
    evidence = {
        "status": "measured",
        "duration_sec": 1,
        "sha256": _sha256(audio),
        "path": str(audio),
    }
    monkeypatch.setattr(package_module, "_probe_media_fd", lambda fd, expected: expected == "audio")
    assert validate_audio_evidence(evidence, root=root)
    evidence["path"] = str(tmp_path / "outside.wav")
    assert not validate_audio_evidence(evidence, root=root)


def test_rejects_invalid_top_level_shape() -> None:
    assert not validate_dialogue_scene_package(
        {"kind": "dialogue-scene-package", "scenes": "not-an-array"}
    )["ok"]


def test_schema_requires_every_runtime_line_field() -> None:
    schema_path = (
        Path(__file__).resolve().parents[1] / "schemas" / "dialogue-scene-package.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    errors = list(
        Draft202012Validator(schema).iter_errors(
            {
                "schema_version": 1,
                "kind": "dialogue-scene-package",
                "mode": "dialogue_drama",
                "scenes": [{"scene_id": "scene01", "lines": [{}]}],
            }
        )
    )

    assert errors

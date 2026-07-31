from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import dialogue_scene_package as package_module  # noqa: E402
from dialogue_benchmark import (  # noqa: E402
    WEAPONS,
    approve_benchmark_parameters,
    build_dialogue_benchmark,
    record_benchmark_arm,
)
from util import write_json  # noqa: E402


def _package(tmp_path: Path, duration: float) -> dict:
    lines = []
    for index in range(4):
        audio_path = tmp_path / f"l{index}.wav"
        audio_path.write_bytes(f"audio-{index}".encode())
        lines.append(
            {
                "line_id": f"l{index}",
                "speaker": "hero",
                "spoken_text": "行く。",
                "caption_text": "我要走。",
                "emotion": "坚定",
                "subtext": "反击",
                "action_while_speaking": "抬眼",
                "listener": "partner",
                "scene_state_id": f"s{index}",
                "screen_mode": "on_camera",
                "lipsync_required": True,
                "audio": {
                    "status": "measured",
                    "duration_sec": duration,
                    "path": str(audio_path),
                    "sha256": hashlib.sha256(audio_path.read_bytes()).hexdigest(),
                },
            }
        )
    return {
        "schema_version": 1,
        "kind": "dialogue-scene-package",
        "mode": "dialogue_drama",
        "scenes": [{"scene_id": "sc01", "lines": lines}],
    }


def test_benchmark_requires_30_seconds_of_measured_rehearsal(tmp_path: Path) -> None:
    write_json(tmp_path / "dialogue-scene-package.json", _package(tmp_path, 5))
    report = build_dialogue_benchmark(tmp_path)
    assert report["status"] == "blocked"
    assert "BENCHMARK_DURATION_INSUFFICIENT" in {blocker["code"] for blocker in report["blockers"]}


def test_benchmark_rejects_duration_only_external_symlink_and_non_media(
    tmp_path: Path,
) -> None:
    duration_only = _package(tmp_path, 10)
    for line in duration_only["scenes"][0]["lines"]:
        line["audio"] = {"duration_sec": 10}
    write_json(tmp_path / "dialogue-scene-package.json", duration_only)
    report = build_dialogue_benchmark(tmp_path)
    assert "BENCHMARK_AUDIO_EVIDENCE_INVALID" in {blocker["code"] for blocker in report["blockers"]}

    outside = tmp_path.parent / "outside.wav"
    outside.write_bytes(b"plain text outside root")
    for name in ("external", "symlink", "non-media"):
        root = tmp_path / name
        root.mkdir()
        package = _package(root, 10)
        if name == "external":
            evidence = outside
        elif name == "symlink":
            evidence = root / "linked.wav"
            evidence.symlink_to(outside)
        else:
            evidence = root / "fake.wav"
            evidence.write_bytes(b"plain text with wav suffix")
        digest = hashlib.sha256(evidence.read_bytes()).hexdigest()
        for line in package["scenes"][0]["lines"]:
            line["audio"].update(path=str(evidence), sha256=digest)
        write_json(root / "dialogue-scene-package.json", package)
        report = build_dialogue_benchmark(root)
        assert report["status"] == "blocked"
        assert "BENCHMARK_AUDIO_EVIDENCE_INVALID" in {
            blocker["code"] for blocker in report["blockers"]
        }


def test_benchmark_plans_same_lines_without_requiring_lipsync(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_json(tmp_path / "dialogue-scene-package.json", _package(tmp_path, 10))
    monkeypatch.setattr(package_module, "_probe_media_fd", lambda fd, expected: expected == "audio")
    report = build_dialogue_benchmark(tmp_path)
    assert report["status"] == "planned"
    assert report["duration_sec"] == 30
    assert [arm["weapon"] for arm in report["arms"]] == [
        "comfy_qwen_i2i_performance_state",
        "comfy_qwen_i2i_keyframe",
        "frw_ltx23_img2video_audio",
    ]


def test_benchmark_rejects_symlinked_or_oversized_package(tmp_path: Path) -> None:
    root = tmp_path / "film"
    root.mkdir()
    outside = tmp_path / "outside.json"
    write_json(outside, _package(tmp_path, 10))
    (root / "dialogue-scene-package.json").symlink_to(outside)
    with pytest.raises(ValueError, match="BENCHMARK_PACKAGE_UNSAFE"):
        build_dialogue_benchmark(root)

    (root / "dialogue-scene-package.json").unlink()
    with (root / "dialogue-scene-package.json").open("wb") as handle:
        handle.truncate(4 * 1024 * 1024 + 1)
    with pytest.raises(ValueError, match="BENCHMARK_PACKAGE_UNSAFE"):
        build_dialogue_benchmark(root)


def test_benchmark_rejects_symlinked_receipt_parent_or_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "film"
    root.mkdir()
    write_json(root / "dialogue-scene-package.json", _package(root, 10))
    monkeypatch.setattr(package_module, "_probe_media_fd", lambda fd, expected: expected == "audio")

    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "receipts").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="BENCHMARK_RECEIPT_PATH_UNSAFE"):
        build_dialogue_benchmark(root)
    assert not (outside / "dialogue-weapon-benchmark.json").exists()

    (root / "receipts").unlink()
    (root / "receipts").mkdir()
    victim = outside / "victim.json"
    victim.write_text("original", encoding="utf-8")
    (root / "receipts" / "dialogue-weapon-benchmark.json").symlink_to(victim)
    with pytest.raises(ValueError, match="BENCHMARK_RECEIPT_PATH_UNSAFE"):
        build_dialogue_benchmark(root)
    assert victim.read_text(encoding="utf-8") == "original"


def test_benchmark_locks_all_three_stage_parameters_after_human_review(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIFILM_AUDIO_RECEIPT_KEY", "test-dialogue-benchmark-signing-key")
    write_json(tmp_path / "dialogue-scene-package.json", _package(tmp_path, 10))
    monkeypatch.setattr(package_module, "_probe_media_fd", lambda fd, expected: expected == "audio")
    build_dialogue_benchmark(tmp_path)
    with pytest.raises(ValueError, match="BENCHMARK_ALL_ARMS_REVIEW_REQUIRED"):
        approve_benchmark_parameters(tmp_path, reviewer="Dex", rationale="looks stable")
    for weapon in WEAPONS:
        artifact = tmp_path / f"{weapon}.mp4"
        artifact.write_bytes(b"review artifact")
        parameters: dict[str, object] = {"seed": 7}
        if weapon == "frw_ltx23_img2video_audio":
            parameters["native_text_review"] = {
                "sampled_frames": ["frames/0001.png", "frames/0060.png"],
                "unexpected_visual_text_detected": False,
                "native_audio_dialogue_matches_expected": True,
                "mouth_audio_sync_approved": True,
                "caption_owner": "hyperframes",
            }
        record_benchmark_arm(
            tmp_path,
            weapon=weapon,
            artifact=artifact,
            reviewer="Dex",
            note="face and motion reviewed",
            parameters=parameters,
        )
    receipt = approve_benchmark_parameters(tmp_path, reviewer="Dex", rationale="stable chain")
    assert receipt["selection"]["status"] == "approved"
    assert set(receipt["selection"]["required_weapons"]) == set(WEAPONS)
    assert set(receipt["selection"]["stable_parameters"]) == set(WEAPONS)
    artifact = tmp_path / f"{WEAPONS[0]}.mp4"
    record_benchmark_arm(
        tmp_path,
        weapon=WEAPONS[0],
        artifact=artifact,
        reviewer="Dex",
        note="rechecked after adjustment",
        parameters={"seed": 999},
    )
    changed = (tmp_path / "receipts" / "dialogue-weapon-benchmark.json").read_text(encoding="utf-8")
    assert '"status": "pending_human_review"' in changed
    assert "receipt_hmac_sha256" not in changed


def test_ltx_benchmark_arm_requires_clean_native_text_review(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_json(tmp_path / "dialogue-scene-package.json", _package(tmp_path, 10))
    monkeypatch.setattr(package_module, "_probe_media_fd", lambda fd, expected: expected == "audio")
    build_dialogue_benchmark(tmp_path)
    artifact = tmp_path / "ltx.mp4"
    artifact.write_bytes(b"review artifact")
    with pytest.raises(ValueError, match="LTX_NATIVE_TEXT_REVIEW_REQUIRED"):
        record_benchmark_arm(
            tmp_path,
            weapon="frw_ltx23_img2video_audio",
            artifact=artifact,
            reviewer="Dex",
            note="reviewed",
            parameters={"seed": 7},
        )

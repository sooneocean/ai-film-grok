from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import jsonschema
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from longform import (  # noqa: E402
    LongformError,
    build_longform_plan,
    estimate_plate_timeout,
    longform_status,
    materialize_unit_masters,
    prepare_longform_resume,
)


def _seed_longform_root(root: Path, *, duration_sec: float = 600.0) -> None:
    shots = []
    for index in range(100):
        shots.append(
            {
                "id": f"shot{index + 1:03d}",
                "beat_id": f"beat{index // 5 + 1:02d}",
                "duration_sec": duration_sec / 100,
            }
        )
    scenes = []
    for index in range(10):
        scenes.append(
            {
                "id": f"scene{index + 1:02d}",
                "title": f"Scene {index + 1}",
                "shots": shots[index * 10 : (index + 1) * 10],
            }
        )
    (root / "receipts").mkdir(parents=True)
    (root / "film-spec.json").write_text(
        json.dumps(
            {
                "title": "Longform",
                "vo_mode": "dialogue_drama",
                "director_intent": {},
                "aspect_ratio": "9:16",
                "production_mode": "longform",
                "longform_profile": {
                    "target_duration_sec": duration_sec,
                    "act_count": 3,
                    "unit_max_duration_sec": 90,
                    "approval_policy": "three_gates",
                },
                "scenes": scenes,
            }
        ),
        encoding="utf-8",
    )
    (root / "drama-graph.json").write_text(
        json.dumps({"schemaVersion": 1, "project": {"production_mode": "longform"}}),
        encoding="utf-8",
    )
    (root / "timeline.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "fps": 30,
                "width": 720,
                "height": 1280,
                "shots": [
                    {"id": shot["id"], "duration_sec": shot["duration_sec"]} for shot in shots
                ],
            }
        ),
        encoding="utf-8",
    )


def _film_spec_schema() -> dict[str, object]:
    return json.loads(
        (Path(__file__).resolve().parents[1] / "schemas" / "film-spec.schema.json").read_text()
    )


def test_build_longform_plan_is_hash_bound_and_unitized(tmp_path: Path) -> None:
    _seed_longform_root(tmp_path)

    plan = build_longform_plan(tmp_path, write=True)

    assert plan["ok"] is True
    assert plan["target_duration_sec"] == pytest.approx(600)
    assert {unit["act_id"] for unit in plan["units"]} == {"act1", "act2", "act3"}
    assert all(unit["duration_sec"] <= 90 for unit in plan["units"])
    assert [shot for unit in plan["units"] for shot in unit["shot_ids"]] == [
        f"shot{index:03d}" for index in range(1, 101)
    ]
    assert plan["units"][0]["approval_gate"] == "pilot_scene"
    assert plan["units"][0]["depends_on"] == []
    assert plan["units"][1]["depends_on"] == [plan["units"][0]["id"]]
    assert plan["workflow_core"]["evidence_policy"] == "hash-bound-fail-closed"
    assert plan["packs"] == {"format": "vertical-longform", "genre": "drama"}
    assert len(plan["source_hashes"]) == 3
    assert len(plan["content_sha256"]) == 64
    assert (tmp_path / "receipts/longform-production-plan.json").is_file()
    schema = json.loads(
        (
            Path(__file__).resolve().parents[1] / "schemas" / "longform-production-plan.schema.json"
        ).read_text()
    )
    jsonschema.Draft202012Validator(schema).validate(plan)

    status = longform_status(tmp_path)
    assert status["ok"] is True
    assert status["checkpoint_corrupt"] is False
    assert status["unit_counts"]["total"] == len(plan["units"])
    assert status["next_unit"]["id"] == plan["units"][0]["id"]


@pytest.mark.parametrize(
    "patch",
    [
        {"aspect_ratio": "16:9"},
        {"longform_profile": None},
    ],
)
def test_film_spec_schema_requires_longform_profile_and_vertical_aspect(
    patch: dict[str, object],
) -> None:
    spec: dict[str, object] = {
        "title": "Longform",
        "vo_mode": "dialogue_drama",
        "director_intent": {},
        "scenes": [],
        "production_mode": "longform",
        "aspect_ratio": "9:16",
        "longform_profile": {
            "target_duration_sec": 600,
            "act_count": 3,
            "unit_max_duration_sec": 90,
            "approval_policy": "three_gates",
        },
    }
    if "longform_profile" in patch and patch["longform_profile"] is None:
        spec.pop("longform_profile")
    else:
        spec.update(patch)

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(_film_spec_schema()).validate(spec)


@pytest.mark.parametrize("duration", [479.99, 900.01])
def test_longform_duration_outside_v1_boundary_fails(tmp_path: Path, duration: float) -> None:
    _seed_longform_root(tmp_path, duration_sec=duration)
    with pytest.raises(LongformError, match="480..900"):
        build_longform_plan(tmp_path)


def test_longform_plan_refuses_source_hash_drift(tmp_path: Path) -> None:
    _seed_longform_root(tmp_path)
    build_longform_plan(tmp_path, write=True)
    timeline = json.loads((tmp_path / "timeline.json").read_text())
    timeline["shots"][0]["duration_sec"] = 12
    (tmp_path / "timeline.json").write_text(json.dumps(timeline), encoding="utf-8")

    status = longform_status(tmp_path)

    assert status["ok"] is False
    assert status["stale"] is True
    assert "timeline" in status["stale_sources"]


def test_longform_plan_refuses_tampered_unit_contract(tmp_path: Path) -> None:
    _seed_longform_root(tmp_path)
    build_longform_plan(tmp_path, write=True)
    path = tmp_path / "receipts" / "longform-production-plan.json"
    plan = json.loads(path.read_text())
    plan["units"][0]["duration_sec"] = 1
    path.write_text(json.dumps(plan), encoding="utf-8")

    status = longform_status(tmp_path)

    assert status["ok"] is False
    assert status["stale_sources"] == ["plan"]
    assert "tampered" in status["error"]


def test_longform_actual_timeline_must_meet_eight_minute_floor(tmp_path: Path) -> None:
    _seed_longform_root(tmp_path, duration_sec=480)
    timeline_path = tmp_path / "timeline.json"
    timeline = json.loads(timeline_path.read_text())
    for shot in timeline["shots"]:
        shot["duration_sec"] = 4.56
    timeline_path.write_text(json.dumps(timeline), encoding="utf-8")

    with pytest.raises(LongformError, match="actual timeline duration"):
        build_longform_plan(tmp_path)


def test_longform_status_does_not_backup_corrupt_checkpoint(tmp_path: Path) -> None:
    _seed_longform_root(tmp_path)
    build_longform_plan(tmp_path, write=True)
    checkpoint_path = tmp_path / "receipts" / "checkpoints" / "final-render.json"
    checkpoint_path.parent.mkdir(parents=True)
    checkpoint_path.write_text("{corrupt", encoding="utf-8")

    status = longform_status(tmp_path)

    assert status["ok"] is False
    assert status["checkpoint_corrupt"] is True
    assert checkpoint_path.read_text(encoding="utf-8") == "{corrupt"
    assert list(checkpoint_path.parent.glob("final-render.json.corrupt.*")) == []


def test_dynamic_plate_timeout_preserves_short_default_and_scales_longform(tmp_path: Path) -> None:
    assert estimate_plate_timeout(tmp_path, duration_sec=60, shot_count=12, lipsync="off") == 1200
    # Wave D: longform clock (≥480s) floors at 1800 even with few shots
    assert estimate_plate_timeout(tmp_path, duration_sec=480, shot_count=10, lipsync="off") >= 1800
    assert (
        estimate_plate_timeout(
            tmp_path,
            duration_sec=600,
            shot_count=100,
            lipsync="auto",
        )
        > 3600
    )


def test_plate_timeout_longform_mode_floor(tmp_path: Path) -> None:
    (tmp_path / "film-spec.json").write_text(
        json.dumps(
            {
                "production_mode": "longform",
                "longform_profile": {"target_duration_sec": 600},
            }
        ),
        encoding="utf-8",
    )
    # short picture estimate but longform mode → still ≥1800
    assert estimate_plate_timeout(tmp_path, duration_sec=90, shot_count=12, lipsync="off") >= 1800


def test_resume_refuses_unit_before_verified_dependency(tmp_path: Path) -> None:
    _seed_longform_root(tmp_path)
    plan = build_longform_plan(tmp_path, write=True)

    with pytest.raises(LongformError, match="dependencies are incomplete"):
        prepare_longform_resume(tmp_path, unit_id=plan["units"][1]["id"])

    ready = prepare_longform_resume(tmp_path, unit_id=plan["units"][0]["id"])
    assert ready["resume_from"] == "first_invalid_stage"
    assert ready.get("completed") is not True
    assert ready["next_action"].endswith('" --resume')


def test_materialize_unit_masters_checkpoints_verified_final_segments(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_longform_root(tmp_path)
    plan = build_longform_plan(tmp_path, write=True)
    final_path = tmp_path / "out" / "film_final.mp4"
    final_path.parent.mkdir(parents=True)
    final_path.write_bytes(b"verified-final")

    def fake_run(command, output, **_kwargs):
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(f"unit:{output_path.stem}".encode())
        return None

    def fake_evidence(path: Path) -> dict[str, object]:
        from util import sha256_file

        return {
            "sha256": sha256_file(path),
            "bytes": path.stat().st_size,
            "duration_sec": 60.0,
            "video": {"codec_name": "h264", "width": 720, "height": 1280},
            "audio_streams": 1,
            "full_decode": True,
        }

    monkeypatch.setattr("longform.run_media_to_output", fake_run)
    monkeypatch.setattr("checkpoint._media_evidence", fake_evidence)
    shots = [{"id": f"shot{index:03d}", "target": 6.0} for index in range(1, 101)]

    result = materialize_unit_masters(
        tmp_path,
        final_path=final_path,
        film_timeline={"shot_starts": [float(index * 6) for index in range(100)]},
        shots=shots,
    )

    assert result["unit_count"] == len(plan["units"])
    assert all(Path(unit["output"]).is_file() for unit in result["units"])
    assert result["units"][0]["start_sec"] == pytest.approx(0)
    assert result["units"][-1]["end_sec"] == pytest.approx(600)
    status = longform_status(tmp_path)
    assert status["unit_counts"] == {
        "total": len(plan["units"]),
        "completed": len(plan["units"]),
        "pending": 0,
    }


def test_unit_master_receipt_invalidates_when_final_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_longform_root(tmp_path)
    plan = build_longform_plan(tmp_path, write=True)
    final_path = tmp_path / "out" / "film_final.mp4"
    final_path.parent.mkdir(parents=True)
    final_path.write_bytes(b"first-final")

    def fake_run(_command, output, **_kwargs):
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"unit")
        return None

    def fake_evidence(path: Path) -> dict[str, object]:
        from util import sha256_file

        return {
            "sha256": sha256_file(path),
            "bytes": path.stat().st_size,
            "duration_sec": 60.0,
            "video": {"codec_name": "h264", "width": 720, "height": 1280},
            "audio_streams": 1,
            "full_decode": True,
        }

    monkeypatch.setattr("longform.run_media_to_output", fake_run)
    monkeypatch.setattr("checkpoint._media_evidence", fake_evidence)
    materialize_unit_masters(
        tmp_path,
        final_path=final_path,
        film_timeline={"shot_starts": [float(index * 6) for index in range(100)]},
        shots=[{"id": f"shot{index:03d}", "target": 6.0} for index in range(1, 101)],
    )
    final_path.write_bytes(b"changed-final")

    status = longform_status(tmp_path)

    assert status["unit_counts"]["completed"] == 0
    assert status["next_unit"]["id"] == plan["units"][0]["id"]


@pytest.mark.slow
def test_real_eight_minute_vertical_media_unit_acceptance(tmp_path: Path) -> None:
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg is required")
    _seed_longform_root(tmp_path, duration_sec=480)
    plan = build_longform_plan(tmp_path, write=True)
    final_path = tmp_path / "out" / "film_final.mp4"
    final_path.parent.mkdir(parents=True)
    subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=0x182033:s=90x160:r=1:d=480",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=220:sample_rate=8000:duration=480",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-crf",
            "35",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(final_path),
        ],
        check=True,
        capture_output=True,
        timeout=120,
    )
    shots = [{"id": f"shot{index:03d}", "target": 4.8} for index in range(1, 101)]

    result = materialize_unit_masters(
        tmp_path,
        final_path=final_path,
        film_timeline={"shot_starts": [float(index * 4.8) for index in range(100)]},
        shots=shots,
    )

    assert result["unit_count"] == len(plan["units"])
    assert longform_status(tmp_path)["unit_counts"]["pending"] == 0
    from media_probe import probe_media

    first = probe_media(Path(result["units"][0]["output"]))
    video = next(stream for stream in first["streams"] if stream["codec_type"] == "video")
    assert (video["width"], video["height"]) == (90, 160)
    assert any(stream["codec_type"] == "audio" for stream in first["streams"])

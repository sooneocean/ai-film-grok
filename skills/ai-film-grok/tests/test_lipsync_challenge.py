from __future__ import annotations

import json
import sys
from pathlib import Path

import jsonschema
import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

from aifilm_grok import build_parser  # noqa: E402
from lipsync_backend import BACKEND_PRIORITY  # noqa: E402
from lipsync_challenge import (  # noqa: E402
    BACKEND_IDS,
    FIXTURE_IDS,
    LipsyncChallengeError,
    build_challenge_report,
    create_blind_package,
    create_challenge,
    record_blind_review,
    register_result,
)

HASHES = {
    "front_closeup": "1" * 64,
    "three_quarter": "2" * 64,
    "occlusion_motion": "3" * 64,
    "anime": "4" * 64,
    "audio": "a" * 64,
}


def _files(root: Path) -> tuple[dict[str, Path], Path, Path]:
    fixtures: dict[str, Path] = {}
    for fixture_id in FIXTURE_IDS:
        path = root / f"{fixture_id}.mp4"
        path.write_bytes(fixture_id.encode())
        fixtures[fixture_id] = path
    audio = root / "dialogue-zh.wav"
    audio.write_bytes(b"audio")
    approval = root / "approval.json"
    approval.write_text(
        json.dumps(
            {
                "approved": True,
                "audio": {
                    "sha256": HASHES["audio"],
                    "language": "zh",
                    "role": "final_character_dialogue",
                },
                "fixtures": {
                    fixture_id: {
                        "sha256": HASHES[fixture_id],
                        "role": "lipsync_challenge_source",
                    }
                    for fixture_id in FIXTURE_IDS
                },
            }
        )
    )
    return fixtures, audio, approval


def _probe_video(path: Path) -> dict[str, object]:
    return {
        "path": str(path),
        "duration_sec": 4.0,
        "width": 720,
        "height": 1280,
        "fps": 25.0,
        "codec": "h264",
        "full_decode": True,
    }


def _probe_audio(path: Path) -> dict[str, object]:
    return {
        "path": str(path),
        "duration_sec": 4.0,
        "sample_rate": 24000,
        "channels": 1,
        "codec": "pcm_s16le",
    }


def _create(root: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    fixtures, audio, approval = _files(root)
    monkeypatch.setattr(
        "lipsync_challenge.sha256",
        lambda path: HASHES["audio"] if path.suffix == ".wav" else HASHES.get(path.stem, "f" * 64),
    )
    monkeypatch.setattr("lipsync_challenge._probe_video", _probe_video)
    monkeypatch.setattr("lipsync_challenge._probe_audio", _probe_audio)
    return create_challenge(
        root,
        fixtures=fixtures,
        japanese_audio=audio,
        approval_receipt=approval,
    )


def _metrics(
    path: Path,
    *,
    output_hash: str,
    source_hash: str,
    backend_id: str,
) -> Path:
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "kind": "ai-film-lipsync-challenge-metrics",
                "backend_id": backend_id,
                "output_sha256": output_hash,
                "source_video_sha256": source_hash,
                "audio_sha256": HASHES["audio"],
                "evaluator": {
                    "name": "challenge-evaluator",
                    "version": "1.0",
                    "model_sha256": "e" * 64,
                },
                "metrics": {
                    "lip_sync_score": 0.9,
                    "lip_sync_offset_frames": 1.0,
                    "lip_sync_confidence": 0.9,
                    "identity_similarity": 0.9,
                    "mouth_temporal_stability": 0.9,
                    "outside_mouth_similarity": 0.9,
                    "teeth_lip_color_stability": 0.9,
                },
            }
        )
    )
    return path


def _runtime(
    path: Path,
    *,
    output_hash: str,
    backend_id: str,
    single_gpu: bool = True,
) -> Path:
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "kind": "ai-film-lipsync-challenge-runtime",
                "backend_id": backend_id,
                "output_sha256": output_hash,
                "executor": "rtx5090-main",
                "gpu_model": "NVIDIA GeForce RTX 5090",
                "gpu_count": 1 if single_gpu else 2,
                "peak_vram_mb": 29000,
                "elapsed_sec": 12.5,
                "completed": True,
            }
        )
    )
    return path


def _register_all(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    backends: tuple[str, ...] = (
        "latentsync-1.6",
        "musetalk-1.5",
    ),
    fixture_ids: tuple[str, ...] = FIXTURE_IDS,
) -> None:
    monkeypatch.setattr("lipsync_challenge._probe_video", _probe_video)
    monkeypatch.setattr("lipsync_challenge._verify_full_decode", lambda _path: None)
    registered_hashes: dict[str, str] = {"challenge.json": "c" * 64}
    for fixture_index, fixture_id in enumerate(fixture_ids):
        for backend_index, backend_id in enumerate(backends):
            output = root / f"{fixture_id}-{backend_id}.mp4"
            output.write_bytes(f"{fixture_id}:{backend_id}".encode())
            output_hash = f"{fixture_index + backend_index + 5:x}"[-1] * 64
            registered_hashes[output.name] = output_hash
            metrics_path = root / f"{fixture_id}-{backend_id}-metrics.json"
            runtime_path = root / f"{fixture_id}-{backend_id}-runtime.json"
            registered_hashes[metrics_path.name] = "d" * 64
            registered_hashes[runtime_path.name] = "b" * 64
            monkeypatch.setattr(
                "lipsync_challenge.sha256",
                lambda path, hashes=registered_hashes: hashes.get(path.name, "f" * 64),
            )
            register_result(
                root,
                fixture_id=fixture_id,
                backend_id=backend_id,
                output=output,
                metrics_receipt=_metrics(
                    metrics_path,
                    output_hash=output_hash,
                    source_hash=HASHES[fixture_id],
                    backend_id=backend_id,
                ),
                runtime_receipt=_runtime(
                    runtime_path,
                    output_hash=output_hash,
                    backend_id=backend_id,
                ),
            )
    monkeypatch.setattr(
        "lipsync_challenge.sha256",
        lambda path: registered_hashes.get(path.name, "f" * 64),
    )


def _review_payload(
    package: dict[str, object],
    *,
    winner_backend: str,
    wins: int,
    hard_failure: str | None = None,
) -> dict[str, object]:
    mapping = json.loads(Path(str(package["private_mapping_path"])).read_text())
    decisions: dict[str, object] = {}
    for index, fixture_id in enumerate(FIXTURE_IDS):
        labels = mapping["fixtures"][fixture_id]["preservation"]
        winner = winner_backend if index < wins else "latentsync-1.6"
        winner_label = next(label for label, backend in labels.items() if backend == winner)
        hard_failures = {label: [] for label in labels}
        if hard_failure and index == 0:
            hard_failures[winner_label] = [hard_failure]
        decisions[fixture_id] = {
            "preservation": {
                "winner_label": winner_label,
                "watched_original_resolution": True,
                "hard_failures": hard_failures,
            }
        }
    return {"mapping_sha256": package["mapping_sha256"], "decisions": decisions}


def test_registry_preserves_latentsync_default_and_separates_lanes() -> None:
    registry = json.loads((SKILL / "registry" / "lipsync-challenge-models.json").read_text())
    backends = {item["id"]: item for item in registry["backends"]}

    assert registry["production_default"] == "latentsync-1.6"
    assert BACKEND_PRIORITY[0] == "latentsync"
    assert set(backends) == set(BACKEND_IDS) | {"ltx-2.3-lipdub"}
    assert backends["musetalk-1.5"]["default_route_change_allowed"] is False
    assert backends["ltx-2.3-lipdub"]["license"]["review_required"] is True
    assert backends["ltx-2.3-lipdub"]["shared_audio_benchmark_eligible"] is False
    assert backends["ltx-2.3-lipdub"]["lane"] == "text_redub_visual_preservation"
    for backend_id in ("echomimic-v3-flash", "longcat-video-avatar-1.5"):
        assert backends[backend_id]["task_type"] == "face_animation_to_audio"
        assert backends[backend_id]["original_video_pixel_preservation"] is False
        assert backends[backend_id]["final_auto_route_eligible"] is False


def test_main_cli_exposes_no_execute_challenge_actions() -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "lipsync-challenge",
            "report",
            "--root",
            "/tmp/lipsync-challenge",
        ]
    )

    assert args.cmd == "lipsync-challenge"
    assert args.lipsync_challenge_action == "report"


def test_shared_audio_challenge_rejects_lipdub_from_both_cli_and_import(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(
            [
                "lipsync-challenge",
                "register-result",
                "--root",
                "/tmp/lipsync-challenge",
                "--fixture-id",
                "front_closeup",
                "--backend-id",
                "ltx-2.3-lipdub",
                "--output",
                "/tmp/output.mp4",
                "--metrics-receipt",
                "/tmp/metrics.json",
                "--runtime-receipt",
                "/tmp/runtime.json",
            ]
        )
    _create(tmp_path, monkeypatch)
    with pytest.raises(LipsyncChallengeError, match="unknown fixture or backend"):
        register_result(
            tmp_path,
            fixture_id="front_closeup",
            backend_id="ltx-2.3-lipdub",
            output=tmp_path / "ignored.mp4",
            metrics_receipt=tmp_path / "ignored-metrics.json",
            runtime_receipt=tmp_path / "ignored-runtime.json",
        )


def test_create_is_four_fixture_no_execute_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    challenge = _create(tmp_path, monkeypatch)

    assert challenge["ok"] is True
    assert challenge["auto_execute"] is False
    assert challenge["gpu_work_authorized"] is False
    assert challenge["production_default"] == "latentsync-1.6"
    assert list(challenge["fixtures"]) == list(FIXTURE_IDS)
    assert len(challenge["planned_cells"]) == len(FIXTURE_IDS) * len(BACKEND_IDS)
    assert all(
        3.0 <= fixture["source_media"]["duration_sec"] <= 5.0
        for fixture in challenge["fixtures"].values()
    )
    jsonschema.Draft202012Validator(
        json.loads((SKILL / "schemas" / "lipsync-challenge.schema.json").read_text())
    ).validate(challenge)


def test_create_rejects_out_of_range_fixture_duration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixtures, audio, approval = _files(tmp_path)
    monkeypatch.setattr(
        "lipsync_challenge.sha256",
        lambda path: HASHES["audio"] if path.suffix == ".wav" else HASHES.get(path.stem, "f" * 64),
    )
    monkeypatch.setattr(
        "lipsync_challenge._probe_video",
        lambda path: {**_probe_video(path), "duration_sec": 5.1},
    )
    monkeypatch.setattr("lipsync_challenge._probe_audio", _probe_audio)

    with pytest.raises(LipsyncChallengeError, match="3-5 seconds"):
        create_challenge(
            tmp_path,
            fixtures=fixtures,
            japanese_audio=audio,
            approval_receipt=approval,
        )


def test_result_binds_metrics_runtime_geometry_and_hashes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _create(tmp_path, monkeypatch)
    output = tmp_path / "output.mp4"
    output.write_bytes(b"output")
    output_hash = "9" * 64
    monkeypatch.setattr("lipsync_challenge.sha256", lambda _path: output_hash)
    monkeypatch.setattr("lipsync_challenge._probe_video", _probe_video)
    monkeypatch.setattr("lipsync_challenge._verify_full_decode", lambda _path: None)

    result = register_result(
        tmp_path,
        fixture_id="front_closeup",
        backend_id="musetalk-1.5",
        output=output,
        metrics_receipt=_metrics(
            tmp_path / "metrics.json",
            output_hash=output_hash,
            source_hash=HASHES["front_closeup"],
            backend_id="musetalk-1.5",
        ),
        runtime_receipt=_runtime(
            tmp_path / "runtime.json",
            output_hash=output_hash,
            backend_id="musetalk-1.5",
        ),
    )

    assert result["ok"] is True
    assert result["output_sha256"] == output_hash
    assert result["automatic_hard_checks"]["geometry_match"] is True
    assert result["automatic_hard_checks"]["fps_match"] is True
    assert result["automatic_hard_checks"]["duration_match"] is True
    assert result["runtime"]["gpu_count"] == 1
    assert result["metrics"]["lip_sync_offset_frames"] == 1.0


def test_result_rejects_metric_receipt_for_different_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _create(tmp_path, monkeypatch)
    output = tmp_path / "output.mp4"
    output.write_bytes(b"output")
    output_hash = "9" * 64
    monkeypatch.setattr("lipsync_challenge.sha256", lambda _path: output_hash)
    monkeypatch.setattr("lipsync_challenge._probe_video", _probe_video)
    monkeypatch.setattr("lipsync_challenge._verify_full_decode", lambda _path: None)

    with pytest.raises(LipsyncChallengeError, match="metrics receipt"):
        register_result(
            tmp_path,
            fixture_id="front_closeup",
            backend_id="musetalk-1.5",
            output=output,
            metrics_receipt=_metrics(
                tmp_path / "metrics.json",
                output_hash="8" * 64,
                source_hash=HASHES["front_closeup"],
                backend_id="musetalk-1.5",
            ),
            runtime_receipt=_runtime(
                tmp_path / "runtime.json",
                output_hash=output_hash,
                backend_id="musetalk-1.5",
            ),
        )


def test_result_rejects_fake_evaluator_and_gpu_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _create(tmp_path, monkeypatch)
    output = tmp_path / "output.mp4"
    output.write_bytes(b"output")
    output_hash = "9" * 64
    monkeypatch.setattr("lipsync_challenge.sha256", lambda _path: output_hash)
    monkeypatch.setattr("lipsync_challenge._probe_video", _probe_video)
    monkeypatch.setattr("lipsync_challenge._verify_full_decode", lambda _path: None)
    metrics = _metrics(
        tmp_path / "metrics.json",
        output_hash=output_hash,
        source_hash=HASHES["front_closeup"],
        backend_id="musetalk-1.5",
    )
    metrics_payload = json.loads(metrics.read_text())
    metrics_payload["evaluator"]["model_sha256"] = "x"
    metrics.write_text(json.dumps(metrics_payload))

    with pytest.raises(LipsyncChallengeError, match="model SHA-256"):
        register_result(
            tmp_path,
            fixture_id="front_closeup",
            backend_id="musetalk-1.5",
            output=output,
            metrics_receipt=metrics,
            runtime_receipt=_runtime(
                tmp_path / "runtime.json",
                output_hash=output_hash,
                backend_id="musetalk-1.5",
            ),
        )

    metrics_payload["evaluator"]["model_sha256"] = "e" * 64
    metrics.write_text(json.dumps(metrics_payload))
    runtime = _runtime(
        tmp_path / "runtime.json",
        output_hash=output_hash,
        backend_id="musetalk-1.5",
    )
    runtime_payload = json.loads(runtime.read_text())
    runtime_payload["gpu_model"] = "not-a-5090-proof"
    runtime.write_text(json.dumps(runtime_payload))
    with pytest.raises(LipsyncChallengeError, match="NVIDIA GeForce RTX 5090"):
        register_result(
            tmp_path,
            fixture_id="front_closeup",
            backend_id="musetalk-1.5",
            output=output,
            metrics_receipt=metrics,
            runtime_receipt=runtime,
        )


def test_geometry_mismatch_is_recorded_as_a_hard_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _create(tmp_path, monkeypatch)
    output = tmp_path / "stretched.mp4"
    output.write_bytes(b"output")
    output_hash = "7" * 64
    monkeypatch.setattr("lipsync_challenge.sha256", lambda _path: output_hash)
    monkeypatch.setattr(
        "lipsync_challenge._probe_video",
        lambda path: {**_probe_video(path), "width": 640},
    )
    monkeypatch.setattr("lipsync_challenge._verify_full_decode", lambda _path: None)

    result = register_result(
        tmp_path,
        fixture_id="front_closeup",
        backend_id="musetalk-1.5",
        output=output,
        metrics_receipt=_metrics(
            tmp_path / "metrics.json",
            output_hash=output_hash,
            source_hash=HASHES["front_closeup"],
            backend_id="musetalk-1.5",
        ),
        runtime_receipt=_runtime(
            tmp_path / "runtime.json",
            output_hash=output_hash,
            backend_id="musetalk-1.5",
        ),
    )
    report = build_challenge_report(tmp_path)

    assert result["ok"] is False
    assert report["backends"]["musetalk-1.5"]["state"] == "blocked_hard_failure"
    assert "geometry_match" in report["backends"]["musetalk-1.5"]["hard_failures"]


def test_blind_package_public_template_does_not_reveal_backends(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _create(tmp_path, monkeypatch)
    _register_all(tmp_path, monkeypatch)
    package = create_blind_package(tmp_path)
    public = json.loads(Path(str(package["public_template_path"])).read_text())

    serialized = json.dumps(public)
    assert "latentsync" not in serialized
    assert "musetalk" not in serialized
    assert "ltx-" not in serialized
    assert "echomimic" not in serialized
    assert "longcat" not in serialized
    assert public["instructions"]["original_resolution_required"] is True
    assert Path(str(package["private_mapping_path"])).is_file()


def test_blind_template_does_not_leak_backend_from_root_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "latentsync-secret-challenge"
    root.mkdir()
    _create(root, monkeypatch)
    _register_all(root, monkeypatch)

    package = create_blind_package(root)
    public = Path(str(package["public_template_path"])).read_text().lower()

    assert "latentsync" not in public
    assert str(root).lower() not in public


def test_blind_package_keeps_whole_frame_lane_independent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _create(tmp_path, monkeypatch)
    _register_all(tmp_path, monkeypatch, backends=BACKEND_IDS)

    package = create_blind_package(tmp_path)
    mapping = json.loads(Path(str(package["private_mapping_path"])).read_text())
    public = json.loads(Path(str(package["public_template_path"])).read_text())

    for fixture_id in FIXTURE_IDS:
        assert set(mapping["fixtures"][fixture_id]) == {
            "preservation",
            "whole_frame_generation",
        }
        assert len(mapping["fixtures"][fixture_id]["whole_frame_generation"]) == 2
    serialized = json.dumps(public).lower()
    assert all(backend_id not in serialized for backend_id in BACKEND_IDS)


def test_partial_whole_frame_lane_cannot_be_blind_packaged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _create(tmp_path, monkeypatch)
    _register_all(tmp_path, monkeypatch)
    _register_all(
        tmp_path,
        monkeypatch,
        backends=("echomimic-v3-flash", "longcat-video-avatar-1.5"),
        fixture_ids=("front_closeup",),
    )

    with pytest.raises(LipsyncChallengeError, match="all eight"):
        create_blind_package(tmp_path)


def test_two_blind_lanes_are_counted_independently(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _create(tmp_path, monkeypatch)
    _register_all(tmp_path, monkeypatch, backends=BACKEND_IDS)
    package = create_blind_package(tmp_path)
    mapping = json.loads(Path(str(package["private_mapping_path"])).read_text())
    decisions: dict[str, object] = {}
    for fixture_id in FIXTURE_IDS:
        fixture_decisions: dict[str, object] = {}
        for lane_name, winner in (
            ("preservation", "musetalk-1.5"),
            ("whole_frame_generation", "echomimic-v3-flash"),
        ):
            labels = mapping["fixtures"][fixture_id][lane_name]
            winner_label = next(
                label for label, backend_id in labels.items() if backend_id == winner
            )
            fixture_decisions[lane_name] = {
                "winner_label": winner_label,
                "watched_original_resolution": True,
                "hard_failures": {label: [] for label in labels},
            }
        decisions[fixture_id] = fixture_decisions
    record_blind_review(
        tmp_path,
        reviewer="director",
        review={"mapping_sha256": package["mapping_sha256"], "decisions": decisions},
    )
    report = build_challenge_report(tmp_path)

    assert report["backends"]["musetalk-1.5"]["human_wins"] == 4
    assert report["backends"]["musetalk-1.5"]["state"] == "production_candidate"
    assert report["backends"]["echomimic-v3-flash"]["human_wins"] == 4
    assert report["backends"]["echomimic-v3-flash"]["state"] == "pilot_only"


def test_report_revalidates_result_and_review_bindings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _create(tmp_path, monkeypatch)
    _register_all(tmp_path, monkeypatch)
    package = create_blind_package(tmp_path)
    record_blind_review(
        tmp_path,
        reviewer="director",
        review=_review_payload(package, winner_backend="musetalk-1.5", wins=4),
    )
    result_path = tmp_path / "results" / "front_closeup" / "musetalk-1.5.json"
    result = json.loads(result_path.read_text())
    result["source_video_sha256"] = "0" * 64
    result_path.write_text(json.dumps(result))

    tampered_result_report = build_challenge_report(tmp_path)

    assert tampered_result_report["backends"]["musetalk-1.5"]["state"] == "blocked_evidence"
    assert tampered_result_report["backends"]["musetalk-1.5"]["evidence_errors"]

    result["source_video_sha256"] = HASHES["front_closeup"]
    result_path.write_text(json.dumps(result))
    review_path = tmp_path / "reviews" / "director.json"
    review = json.loads(review_path.read_text())
    review["mapping_sha256"] = "0" * 64
    review_path.write_text(json.dumps(review))

    tampered_review_report = build_challenge_report(tmp_path)

    assert tampered_review_report["backends"]["musetalk-1.5"]["state"] == "blocked_evidence"


def test_human_hard_failure_blocks_even_four_of_four_wins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _create(tmp_path, monkeypatch)
    _register_all(tmp_path, monkeypatch)
    package = create_blind_package(tmp_path)
    record_blind_review(
        tmp_path,
        reviewer="director",
        review=_review_payload(
            package,
            winner_backend="musetalk-1.5",
            wins=4,
            hard_failure="teeth_lip_color_drift",
        ),
    )

    report = build_challenge_report(tmp_path)

    assert report["backends"]["musetalk-1.5"]["state"] == "blocked_hard_failure"
    assert report["backends"]["musetalk-1.5"]["human_wins"] == 4
    assert report["route_change_submission_ready"] is False


def test_generative_backends_can_never_enter_final_auto_route(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _create(tmp_path, monkeypatch)
    report = build_challenge_report(tmp_path)

    for backend_id in ("echomimic-v3-flash", "longcat-video-avatar-1.5"):
        backend = report["backends"][backend_id]
        assert backend["task_type"] == "face_animation_to_audio"
        assert backend["state"] == "pilot_only"
        assert backend["final_auto_route_eligible"] is False
    assert report["production_default"] == "latentsync-1.6"

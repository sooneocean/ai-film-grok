from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import master_delivery  # noqa: E402
from approval_ledger import append_approval  # noqa: E402
from master_delivery import validate_master_delivery  # noqa: E402


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _project(root: Path) -> tuple[dict, dict]:
    files = [
        "film_final.mp4",
        "final.srt",
        "drama-graph.json",
        "style-bible.json",
        "audio-bible.json",
        "post-bible.json",
        "film-spec.json",
        "edit.edl",
        "provenance.json",
    ]
    for rel in files:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"fixture:{rel}".encode())
    final_hash = _sha(root / "film_final.mp4")
    srt_hash = _sha(root / "final.srt")
    approval = append_approval(
        root,
        scope="master",
        approval_type="master_lock",
        approver_type="user",
        approver="dex",
        user_phrase="完整看完，批准",
        input_hashes={rel: _sha(root / rel) for rel in files},
        evidence_refs=["review/full-screening.json"],
        transaction_id="master-screening-001",
    )
    files.append("receipts/approval-ledger.json")
    motion_evidence = root / "review" / "motion-delta.json"
    caption_frame = root / "review" / "caption-frame.png"
    motion_evidence.parent.mkdir(parents=True, exist_ok=True)
    motion_evidence.write_text('{"score":0.21}', encoding="utf-8")
    caption_frame.write_bytes(b"caption-frame")
    delivery = {
        "assets": {rel: _sha(root / rel) for rel in files},
        "motion_evidence": [
            {
                "kind": "decoded-frame-delta",
                "score": 0.21,
                "final_sha256": final_hash,
                "evidence_ref": "review/motion-delta.json",
                "evidence_sha256": _sha(motion_evidence),
            }
        ],
        "caption_attestation": {
            "visible": True,
            "final_sha256": final_hash,
            "srt_sha256": srt_hash,
            "frame_ref": "review/caption-frame.png",
            "frame_sha256": _sha(caption_frame),
        },
        "full_screening": {
            "approval_ref": approval["approval_id"],
        },
    }
    ffprobe = {
        "format": {"duration": "45.0"},
        "streams": [
            {"codec_type": "video", "width": 720, "height": 1280, "avg_frame_rate": "30/1"},
            {"codec_type": "audio", "codec_name": "aac", "channels": 2},
        ],
    }
    return delivery, ffprobe


def _mock_readback(monkeypatch: pytest.MonkeyPatch, ffprobe: dict) -> None:
    monkeypatch.setattr(master_delivery, "_run_ffprobe", lambda _path: ffprobe)
    monkeypatch.setattr(master_delivery, "_full_decode", lambda _path: None)


def test_master_gate_requires_motion_audio_captions_and_full_screening(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    delivery, ffprobe = _project(tmp_path)
    _mock_readback(monkeypatch, ffprobe)
    report = validate_master_delivery(tmp_path, delivery=delivery)
    assert report["ok"], report["issues"]
    assert report["duration_sec"] == 45.0


def test_replacing_final_invalidates_all_bound_approvals(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    delivery, ffprobe = _project(tmp_path)
    _mock_readback(monkeypatch, ffprobe)
    (tmp_path / "film_final.mp4").write_bytes(b"replacement")
    codes = {
        item["code"] for item in validate_master_delivery(tmp_path, delivery=delivery)["issues"]
    }
    assert {
        "ASSET_HASH_MISMATCH",
        "MOTION_EVIDENCE_STALE",
        "CAPTION_ATTESTATION_STALE",
        "SCREENING_APPROVAL_STALE",
    }.issubset(codes)


def test_missing_audio_or_non_vertical_video_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    delivery, ffprobe = _project(tmp_path)
    ffprobe["streams"] = [{"codec_type": "video", "width": 1280, "height": 720}]
    _mock_readback(monkeypatch, ffprobe)
    codes = {
        item["code"] for item in validate_master_delivery(tmp_path, delivery=delivery)["issues"]
    }
    assert "AUDIO_STREAM_MISSING" in codes
    assert "ASPECT_NOT_VERTICAL" in codes


def test_model_score_cannot_replace_full_screening(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    delivery, ffprobe = _project(tmp_path)
    _mock_readback(monkeypatch, ffprobe)
    delivery["full_screening"] = {"approved": True, "approver_type": "model", "score": 0.99}
    codes = {
        item["code"] for item in validate_master_delivery(tmp_path, delivery=delivery)["issues"]
    }
    assert "FULL_SCREENING_MISSING" in codes


def test_fake_mp4_cannot_pass_with_caller_authored_evidence(tmp_path: Path) -> None:
    delivery, _ffprobe = _project(tmp_path)

    codes = {
        item["code"] for item in validate_master_delivery(tmp_path, delivery=delivery)["issues"]
    }

    assert "MASTER_READBACK_FAILED" in codes

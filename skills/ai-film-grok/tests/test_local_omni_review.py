from __future__ import annotations

import base64
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import local_omni_review  # noqa: E402


def _workspace(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "film"
    root.mkdir()
    frame = root / "frame.jpg"
    frame.write_bytes(b"safe-frame-bytes")
    index = root / "frames.json"
    index.write_text(
        json.dumps({"frames": [{"path": "frame.jpg", "timestamp_sec": 1.25}]}),
        encoding="utf-8",
    )
    return root, index


def test_probe_is_read_only_and_reports_model_presence() -> None:
    with patch.object(
        local_omni_review,
        "_request_json",
        return_value={"data": [{"id": "nvidia/nemotron-nano-3-30b-a3b"}]},
    ) as request:
        report = local_omni_review.probe("http://192.168.88.52:1234/v1")
    assert report["ok"] is True
    assert report["inference_started"] is False
    request.assert_called_once()


def test_review_writes_hash_bound_candidate_only_report(tmp_path: Path) -> None:
    root, index = _workspace(tmp_path)
    response = {
        "choices": [
            {
                "finish_reason": "stop",
                "message": {
                    "content": json.dumps(
                        {"issues": [{"frame_index": 0, "code": "frozen_frame", "note": "疑似静止"}]}
                    )
                },
            }
        ],
        "usage": {"total_tokens": 12, "api_key": "must-not-leak"},
    }
    with patch.object(local_omni_review, "_request_json", return_value=response) as request:
        report = local_omni_review.review_frames(
            root,
            "http://192.168.88.52:1234/v1",
            frame_index=index,
            sanitized=True,
        )
    assert report["status"] == "candidate_only"
    assert report["may_approve_production"] is False
    assert report["candidate_findings"][0]["timestamp_sec"] == 1.25
    assert report["usage"] == {"total_tokens": 12}
    assert Path(report["path"]).is_file()
    body = request.call_args.kwargs["body"]
    image_url = body["messages"][1]["content"][1]["image_url"]["url"]
    assert base64.b64decode(image_url.split(",", 1)[1]) == b"safe-frame-bytes"


def test_review_requires_explicit_sanitization_and_rejects_outside_frame(tmp_path: Path) -> None:
    root, index = _workspace(tmp_path)
    with pytest.raises(local_omni_review.LocalOmniReviewError, match="sanitized"):
        local_omni_review.review_frames(
            root, "http://192.168.88.52:1234/v1", frame_index=index, sanitized=False
        )
    outside = tmp_path / "outside.jpg"
    outside.write_bytes(b"outside")
    index.write_text(
        json.dumps({"frames": [{"path": str(outside), "timestamp_sec": 1.0}]}), encoding="utf-8"
    )
    with pytest.raises(local_omni_review.LocalOmniReviewError, match="inside the film workspace"):
        local_omni_review.review_frames(
            root, "http://192.168.88.52:1234/v1", frame_index=index, sanitized=True
        )


def test_review_rejects_non_stop_or_invalid_issue_schema(tmp_path: Path) -> None:
    root, index = _workspace(tmp_path)
    with patch.object(
        local_omni_review,
        "_request_json",
        return_value={"choices": [{"finish_reason": "length", "message": {"content": "{}"}}]},
    ):
        with pytest.raises(local_omni_review.LocalOmniReviewError, match="finish normally"):
            local_omni_review.review_frames(
                root, "http://192.168.88.52:1234/v1", frame_index=index, sanitized=True
            )
    with patch.object(
        local_omni_review,
        "_request_json",
        return_value={
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {"content": '{"issues":[{"frame_index":9,"code":"x","note":"y"}]}'},
                }
            ]
        },
    ):
        with pytest.raises(local_omni_review.LocalOmniReviewError, match="valid review JSON"):
            local_omni_review.review_frames(
                root, "http://192.168.88.52:1234/v1", frame_index=index, sanitized=True
            )

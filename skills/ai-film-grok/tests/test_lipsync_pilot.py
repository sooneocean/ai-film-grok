from __future__ import annotations

import json
import sys
from hashlib import sha256
from pathlib import Path
from unittest import mock

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from lipsync_pilot import LipsyncPilotError, create_pilot, review_template, run_pilot  # noqa: E402


def _inputs(tmp_path: Path) -> dict[str, Path]:
    values = {}
    for name in ("front", "three", "moving", "audio"):
        path = tmp_path / f"{name}.{'wav' if name == 'audio' else 'mp4'}"
        path.write_bytes(name.encode())
        values[name] = path
    return values


def _approval(tmp_path: Path, inputs: dict[str, Path]) -> Path:
    path = tmp_path / "approval.json"
    path.write_text(
        json.dumps(
            {
                "approved": True,
                "videos": {
                    "front_closeup": {
                        "role": "approved_character_reference",
                        "sha256": sha256(inputs["front"].read_bytes()).hexdigest(),
                    },
                    "three_quarter_closeup": {
                        "role": "approved_character_reference",
                        "sha256": sha256(inputs["three"].read_bytes()).hexdigest(),
                    },
                    "moving_closeup": {
                        "role": "approved_character_reference",
                        "sha256": sha256(inputs["moving"].read_bytes()).hexdigest(),
                    },
                },
                "audio": {
                    "role": "final_character_dialogue",
                    "language": "ja",
                    "sha256": sha256(inputs["audio"].read_bytes()).hexdigest(),
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def _create(root: Path, inputs: dict[str, Path]) -> None:
    with mock.patch("lipsync_pilot._input_media", return_value={"duration": 1.0}):
        create_pilot(
            root,
            front_video=inputs["front"],
            three_quarter_video=inputs["three"],
            moving_video=inputs["moving"],
            japanese_audio=inputs["audio"],
            approval_receipt=_approval(root.parent, inputs),
        )


def test_create_requires_distinct_standard_videos(tmp_path: Path) -> None:
    inputs = _inputs(tmp_path)
    with mock.patch("lipsync_pilot._input_media", return_value={"duration": 1.0}):
        with pytest.raises(LipsyncPilotError, match="distinct"):
            create_pilot(
                tmp_path / "pilot",
                front_video=inputs["front"],
                three_quarter_video=inputs["front"],
                moving_video=inputs["moving"],
                japanese_audio=inputs["audio"],
                approval_receipt=_approval(tmp_path, inputs),
            )


def test_run_blocks_before_node_render_when_comfy_queue_is_busy(tmp_path: Path) -> None:
    inputs = _inputs(tmp_path)
    root = tmp_path / "pilot"
    _create(root, inputs)
    with mock.patch(
        "lipsync_pilot._comfy_is_idle",
        side_effect=LipsyncPilotError("shared ComfyUI queue is not empty"),
    ):
        report = run_pilot(root)
    assert report["state"] == "blocked_queue"
    assert "queue" in report["blocker"]


def test_review_template_only_includes_rendered_candidates(tmp_path: Path) -> None:
    inputs = _inputs(tmp_path)
    root = tmp_path / "pilot"
    _create(root, inputs)
    receipt = root / "receipts" / "lipsync-near-dialogue-pilot.json"
    value = json.loads(receipt.read_text())
    value["samples"]["front_closeup"]["status"] = "pending_human_review"
    receipt.write_text(json.dumps(value), encoding="utf-8")
    template = review_template(root)
    assert set(template["samples"]) == {"front_closeup"}
    assert template["state"] == "pending_human_review"

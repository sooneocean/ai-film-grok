from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import interactive_orchestration as interactive  # noqa: E402


def _snapshot(root: Path, *, status: str = "ready", resource: str = "cloud") -> None:
    (root / "receipts").mkdir()
    (root / "receipts" / "capability-snapshot.json").write_text(
        json.dumps(
            {
                "kind": "ai-film-capability-snapshot",
                "capabilities": [
                    {
                        "id": "frw_cloud",
                        "provider": "frw",
                        "model": "ltx",
                        "resource": resource,
                        "status": status,
                        "authorization": "ready",
                        "pilot_verified": True,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def test_failed_cloud_task_is_retained_without_local_fallback(tmp_path: Path) -> None:
    _snapshot(tmp_path)
    interactive.submit_cloud_candidate(
        tmp_path, candidate_id="c1", shot_id="shot1", capability_id="frw_cloud", task_id="task1"
    )
    report = interactive.record_task_failure(tmp_path, candidate_id="c1", error_code="TASK_FAILED")

    assert report["candidates"][0]["status"] == "failed"
    assert report["candidates"][0]["error_code"] == "TASK_FAILED"
    assert "local" not in json.dumps(report).lower()


def test_terminal_media_must_stay_in_workspace_and_pass_decode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _snapshot(tmp_path)
    interactive.submit_cloud_candidate(
        tmp_path, candidate_id="c1", shot_id="shot1", capability_id="frw_cloud", task_id="task1"
    )
    with pytest.raises(interactive.InteractiveOrchestrationError):
        interactive.record_terminal_media(tmp_path, candidate_id="c1", media_path="/etc/passwd")
    media = tmp_path / "out" / "candidate.mp4"
    media.parent.mkdir()
    media.write_bytes(b"candidate")
    qa_args: dict[str, object] = {}

    def fake_analyze(*_args: object, **kwargs: object) -> dict[str, object]:
        qa_args.update(kwargs)
        return {
            "ok": True,
            "decode_ok": True,
            "duration_sec": 5,
            "has_audio": True,
            "errors": [],
        }

    monkeypatch.setattr(interactive, "analyze_media", fake_analyze)

    report = interactive.record_terminal_media(
        tmp_path, candidate_id="c1", media_path="out/candidate.mp4"
    )

    assert report["candidates"][0]["status"] == "reviewable"
    assert report["candidates"][0]["media_path"] == "out/candidate.mp4"
    assert qa_args["min_width"] == 704
    assert qa_args["min_height"] == 1280


def test_non_cloud_capability_cannot_enter_cloud_queue(tmp_path: Path) -> None:
    _snapshot(tmp_path, resource="local")
    with pytest.raises(interactive.InteractiveOrchestrationError, match="cloud resource"):
        interactive.submit_cloud_candidate(
            tmp_path,
            candidate_id="c1",
            shot_id="shot1",
            capability_id="frw_cloud",
            task_id="task1",
        )


def test_approval_requires_reviewable_cloud_candidate(tmp_path: Path) -> None:
    _snapshot(tmp_path)
    interactive.submit_cloud_candidate(
        tmp_path, candidate_id="c1", shot_id="shot1", capability_id="frw_cloud", task_id="task1"
    )

    with pytest.raises(interactive.InteractiveOrchestrationError):
        interactive.assert_review_action_allowed(tmp_path, stage="shot:shot1", action="approve")

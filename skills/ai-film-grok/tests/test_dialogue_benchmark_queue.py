from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from dialogue_benchmark import WEAPONS  # noqa: E402
from dialogue_benchmark_queue import (  # noqa: E402
    DialogueBenchmarkQueueError,
    claim,
    complete,
    enqueue,
    status,
)
from util import write_json  # noqa: E402


def _fixture(root: Path) -> None:
    write_json(root / "dialogue-scene-package.json", {"kind": "dialogue-scene-package"})
    write_json(
        root / "receipts" / "dialogue-weapon-benchmark.json",
        {
            "kind": "dialogue-weapon-benchmark",
            "status": "planned",
            "duration_sec": 30.0,
            "line_ids": ["sc01_ln01"],
            "weapons": list(WEAPONS),
            "arms": [{"weapon": weapon, "status": "pending"} for weapon in WEAPONS],
        },
    )


def test_enqueue_is_persistent_idempotent_and_never_submits_comfy(tmp_path: Path) -> None:
    _fixture(tmp_path)
    first = enqueue(tmp_path)
    second = enqueue(tmp_path)
    assert first["comfy_prompt_submitted"] is False
    assert len(first["jobs"]) == len(WEAPONS)
    assert len(status(tmp_path)["jobs"]) == len(WEAPONS)
    assert second["jobs"] == first["jobs"]


def test_claim_keeps_job_pending_when_capacity_is_blocked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fixture(tmp_path)
    enqueue(tmp_path)

    class Config:
        comfyui_base_url = "http://127.0.0.1:18188"

    monkeypatch.setattr("config_loader.get_config", lambda: Config())
    monkeypatch.setattr(
        "comfy_video.submission_capacity",
        lambda _url: {"ok": False, "blockers": [{"code": "COMFY_QUEUE_BUSY"}]},
    )
    result = claim(tmp_path)
    assert result["status"] == "deferred"
    assert status(tmp_path)["counts"]["pending"] == len(WEAPONS)


def test_claim_marks_only_one_job_running_when_capacity_is_ready(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fixture(tmp_path)
    enqueue(tmp_path)

    class Config:
        comfyui_base_url = "http://127.0.0.1:18188"

    monkeypatch.setattr("config_loader.get_config", lambda: Config())
    monkeypatch.setattr("comfy_video.submission_capacity", lambda _url: {"ok": True})
    result = claim(tmp_path)
    assert result["status"] == "claimed"
    assert result["comfy_prompt_submitted"] is False
    assert status(tmp_path)["counts"]["running"] == 1


def test_concurrent_claim_does_not_double_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fixture(tmp_path)
    enqueue(tmp_path)

    class Config:
        comfyui_base_url = "http://127.0.0.1:18188"

    monkeypatch.setattr("config_loader.get_config", lambda: Config())
    monkeypatch.setattr("comfy_video.submission_capacity", lambda _url: {"ok": True})

    def try_claim(_: int) -> dict[str, object]:
        try:
            return claim(tmp_path)
        except DialogueBenchmarkQueueError as exc:
            return {"status": "blocked", "reason": str(exc)}

    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(try_claim, range(2)))
    assert sum(result.get("status") == "claimed" for result in results) == 1
    assert status(tmp_path)["counts"]["running"] == 1


def test_complete_rejects_review_without_real_artifact_evidence(tmp_path: Path) -> None:
    _fixture(tmp_path)
    queued = enqueue(tmp_path)["jobs"][0]
    queue = status(tmp_path)["jobs"]
    queue[0].update(status="running", claim_token="valid-token")
    write_json(
        tmp_path / "receipts" / "dialogue-benchmark-queue.json",
        {"schema_version": 1, "kind": "dialogue-benchmark-queue", "jobs": queue},
    )
    receipt = tmp_path / "receipts" / "dialogue-weapon-benchmark.json"
    import json

    report = json.loads(receipt.read_text(encoding="utf-8"))
    report["arms"][0]["status"] = "reviewed"
    write_json(receipt, report)
    with pytest.raises(DialogueBenchmarkQueueError, match="REVIEW_EVIDENCE_INVALID"):
        complete(tmp_path, job_id=queued["id"], claim_token="valid-token")

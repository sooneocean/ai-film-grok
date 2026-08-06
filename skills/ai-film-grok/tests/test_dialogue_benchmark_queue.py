from __future__ import annotations

import json
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
    submit_comfy,
)
from runtime_policy import sha256  # noqa: E402
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


def test_frw_arm_claim_does_not_require_comfy_capacity(tmp_path: Path) -> None:
    _fixture(tmp_path)
    jobs = enqueue(tmp_path)["jobs"]
    for job in jobs[:-1]:
        job["status"] = "succeeded"
    write_json(
        tmp_path / "receipts" / "dialogue-benchmark-queue.json",
        {"schema_version": 1, "kind": "dialogue-benchmark-queue", "jobs": jobs},
    )
    result = claim(tmp_path)
    assert result["status"] == "claimed"
    assert result["job"]["weapon"] == "frw_ltx23_img2video_audio"
    assert result["capacity"] == {"ok": True, "status": "not_required", "executor": "frw"}


def test_claim_rejects_job_bound_to_a_replaced_benchmark(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fixture(tmp_path)
    enqueue(tmp_path)
    receipt = tmp_path / "receipts" / "dialogue-weapon-benchmark.json"
    report = json.loads(receipt.read_text(encoding="utf-8"))
    report["line_ids"] = ["sc01_ln02"]
    write_json(receipt, report)

    class Config:
        comfyui_base_url = "http://127.0.0.1:18188"

    monkeypatch.setattr("config_loader.get_config", lambda: Config())
    monkeypatch.setattr("comfy_video.submission_capacity", lambda _url: {"ok": True})
    with pytest.raises(DialogueBenchmarkQueueError, match="BENCHMARK_MISMATCH"):
        claim(tmp_path)
    assert status(tmp_path)["counts"]["running"] == 0


def test_claim_allows_pending_arm_after_human_review_rewrites_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fixture(tmp_path)
    enqueue(tmp_path)
    receipt = tmp_path / "receipts" / "dialogue-weapon-benchmark.json"
    report = json.loads(receipt.read_text(encoding="utf-8"))
    report["arms"][0]["review_note"] = "approved state"
    write_json(receipt, report)

    class Config:
        comfyui_base_url = "http://127.0.0.1:18188"

    monkeypatch.setattr("config_loader.get_config", lambda: Config())
    monkeypatch.setattr("comfy_video.submission_capacity", lambda _url: {"ok": True})
    result = claim(tmp_path)
    assert result["status"] == "claimed"
    assert result["job"]["weapon"] == WEAPONS[0]


def test_submit_rejects_claim_after_benchmark_is_replaced(tmp_path: Path) -> None:
    _fixture(tmp_path)
    job = enqueue(tmp_path)["jobs"][0]
    queue = status(tmp_path)["jobs"]
    queue[0].update(status="running", claim_token="valid-token", executor="comfy")
    write_json(
        tmp_path / "receipts" / "dialogue-benchmark-queue.json",
        {"schema_version": 1, "kind": "dialogue-benchmark-queue", "jobs": queue},
    )
    workflow = tmp_path / "workflow.json"
    write_json(workflow, {})
    receipt = tmp_path / "receipts" / "dialogue-weapon-benchmark.json"
    report = json.loads(receipt.read_text(encoding="utf-8"))
    report["line_ids"] = ["sc01_ln02"]
    write_json(receipt, report)

    with pytest.raises(DialogueBenchmarkQueueError, match="SUBMISSION_INVALID"):
        submit_comfy(
            tmp_path,
            job_id=job["id"],
            claim_token="valid-token",
            workflow=workflow,
            weapon_id="qwen-image-edit-2511-local",
        )


def test_rejects_duplicate_weapons_in_benchmark_receipt(tmp_path: Path) -> None:
    _fixture(tmp_path)
    receipt = tmp_path / "receipts" / "dialogue-weapon-benchmark.json"
    report = json.loads(receipt.read_text(encoding="utf-8"))
    report["weapons"].append(report["weapons"][0])
    write_json(receipt, report)
    with pytest.raises(DialogueBenchmarkQueueError, match="NOT_QUEUEABLE"):
        enqueue(tmp_path)


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


def test_complete_allows_same_benchmark_after_its_human_review_rewrites_receipt(
    tmp_path: Path,
) -> None:
    _fixture(tmp_path)
    queued = enqueue(tmp_path)["jobs"][0]
    queue = status(tmp_path)["jobs"]
    queue[0].update(status="running", claim_token="valid-token")
    write_json(
        tmp_path / "receipts" / "dialogue-benchmark-queue.json",
        {"schema_version": 1, "kind": "dialogue-benchmark-queue", "jobs": queue},
    )
    artifact = tmp_path / "qwen-state.png"
    artifact.write_bytes(b"reviewed state")
    receipt = tmp_path / "receipts" / "dialogue-weapon-benchmark.json"
    report = json.loads(receipt.read_text(encoding="utf-8"))
    report["arms"][0].update(
        status="reviewed",
        reviewer="Dex",
        review_note="approved",
        artifact="qwen-state.png",
        artifact_sha256=sha256(artifact),
        stable_parameters={"seed": 7},
    )
    write_json(receipt, report)
    result = complete(tmp_path, job_id=queued["id"], claim_token="valid-token")
    assert result["status"] == "succeeded"


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
    report = json.loads(receipt.read_text(encoding="utf-8"))
    report["arms"][0]["status"] = "reviewed"
    write_json(receipt, report)
    queue[0]["benchmark_sha256"] = sha256(receipt)
    write_json(
        tmp_path / "receipts" / "dialogue-benchmark-queue.json",
        {"schema_version": 1, "kind": "dialogue-benchmark-queue", "jobs": queue},
    )
    with pytest.raises(DialogueBenchmarkQueueError, match="REVIEW_EVIDENCE_INVALID"):
        complete(tmp_path, job_id=queued["id"], claim_token="valid-token")

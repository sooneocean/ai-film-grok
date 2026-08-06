from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import skill_runner  # noqa: E402
from approval_ledger import append_approval  # noqa: E402
from skill_runner import RunnerSpec, run_skill  # noqa: E402
from transaction_receipt import stable_hash  # noqa: E402


def test_cli_skill_run_dry_run_roundtrip(tmp_path: Path, capsys) -> None:
    from aifilm_grok import main

    payload_path = tmp_path / "request.json"
    payload_path.write_text(
        json.dumps(
            {
                "skillId": "dispatch.orchestrate",
                "projectRoot": str(tmp_path),
                "nodeRef": "project",
            }
        ),
        encoding="utf-8",
    )
    code = main(
        [
            "skill",
            "run",
            "--skill-id",
            "dispatch.orchestrate",
            "--payload-file",
            str(payload_path),
            "--dry-run",
        ]
    )
    assert code == 0
    assert json.loads(capsys.readouterr().out)["dry_run"] is True


def test_dry_run_validates_contract_and_uses_fixed_runner(tmp_path: Path) -> None:
    payload_path = tmp_path / "request.json"
    payload_path.write_text(
        json.dumps(
            {
                "skillId": "dispatch.orchestrate",
                "projectRoot": str(tmp_path),
                "nodeRef": "project",
                "input": {},
            }
        ),
        encoding="utf-8",
    )
    report = run_skill("dispatch.orchestrate", payload_path, dry_run=True)
    assert report["ok"] is True
    assert report["dry_run"] is True
    assert report["runner"]["operation"] == "dispatch"
    assert report["transaction_id"].startswith("tx-")


def test_media_skills_compile_to_standalone_queue_commands(tmp_path: Path) -> None:
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("locked prompt", encoding="utf-8")
    still = tmp_path / "shot01.png"
    still.write_bytes(b"still")

    keyframe_payload = tmp_path / "keyframe.json"
    keyframe_payload.write_text(
        json.dumps(
            {
                "skillId": "keyframe.generate",
                "projectRoot": str(tmp_path),
                "nodeRef": "shot:shot01",
                "input": {"operation": "image_gen", "promptFile": "prompt.txt"},
            }
        ),
        encoding="utf-8",
    )
    animate_payload = tmp_path / "animate.json"
    animate_payload.write_text(
        json.dumps(
            {
                "skillId": "image.animate",
                "projectRoot": str(tmp_path),
                "nodeRef": "shot:shot01",
                "input": {
                    "operation": "image_to_video",
                    "promptFile": "prompt.txt",
                    "inputs": ["shot01.png"],
                },
            }
        ),
        encoding="utf-8",
    )

    keyframe = run_skill("keyframe.generate", keyframe_payload, dry_run=True)
    animate = run_skill("image.animate", animate_payload, dry_run=True)

    assert keyframe["runner"]["operation"] == "media-queue.add"
    assert Path(keyframe["runner"]["argv"][0]).name == "media-queue"
    assert keyframe["runner"]["argv"][1:3] == ["add", "--root"]
    assert "image_gen" in keyframe["runner"]["argv"]
    assert Path(animate["runner"]["argv"][0]).name == "media-queue"
    assert "image_to_video" in animate["runner"]["argv"]
    assert str(still) in animate["runner"]["argv"]


def test_unknown_skill_is_rejected_without_executing_text(tmp_path: Path) -> None:
    payload = tmp_path / "request.json"
    payload.write_text(
        '{"skillId":"__import__.system","projectRoot":"/tmp","nodeRef":"project"}',
        encoding="utf-8",
    )
    report = run_skill("__import__.system", payload, dry_run=True)
    assert report["ok"] is False
    assert "unknown skill" in report["error"]


def test_payload_dry_run_is_zero_write_and_never_calls_runner(tmp_path: Path, monkeypatch) -> None:
    calls = []

    def fake_runner(payload, _spec):
        calls.append(payload)
        return {"ok": True}

    monkeypatch.setitem(
        skill_runner.RUNNERS,
        "dispatch.orchestrate",
        RunnerSpec("dispatch", (), "local", "none", fake_runner),
    )
    payload_path = tmp_path / "request.json"
    payload_path.write_text(
        json.dumps(
            {
                "skillId": "dispatch.orchestrate",
                "projectRoot": str(tmp_path),
                "nodeRef": "project",
                "input": {},
                "dryRun": True,
            }
        ),
        encoding="utf-8",
    )

    report = run_skill("dispatch.orchestrate", payload_path)

    assert report["dry_run"] is True
    assert calls == []
    assert not (tmp_path / "receipts").exists()


def test_paid_runner_rejects_fake_approval_before_provider_call(
    tmp_path: Path, monkeypatch
) -> None:
    calls = []

    def fake_runner(payload, _spec):
        calls.append(payload)
        return {"ok": True}

    monkeypatch.setitem(
        skill_runner.RUNNERS,
        "image.animate",
        RunnerSpec("media-queue", (), "paid", "human_required", fake_runner),
    )
    payload_path = tmp_path / "request.json"
    payload_path.write_text(
        json.dumps(
            {
                "skillId": "image.animate",
                "projectRoot": str(tmp_path),
                "nodeRef": "shot01",
                "input": {"prompt": "move"},
                "approvalRef": "approval-does-not-exist",
                "spendScope": {
                    "shotIds": ["shot01"],
                    "candidateCount": 1,
                    "budget": {"maxUnits": 1, "currency": "credits"},
                },
            }
        ),
        encoding="utf-8",
    )

    report = run_skill("image.animate", payload_path)

    assert report["ok"] is False
    assert calls == []


def test_paid_runner_uses_exact_current_scope_and_records_approval(
    tmp_path: Path, monkeypatch
) -> None:
    calls = []

    def fake_runner(payload, _spec):
        calls.append(payload)
        return {"ok": True, "assets": []}

    monkeypatch.setitem(
        skill_runner.RUNNERS,
        "image.animate",
        RunnerSpec("media-queue", (), "paid", "human_required", fake_runner),
    )
    input_data = {"prompt": "move"}
    spend_scope = {
        "shotIds": ["shot01"],
        "candidateCount": 1,
        "budget": {"maxUnits": 1, "currency": "credits"},
    }
    approval = append_approval(
        tmp_path,
        scope="skill:image.animate:shot01",
        approval_type="skill_run",
        approver_type="user",
        approver="dex",
        user_phrase="批准 shot01 一个候选，预算一单位",
        input_hashes={"input": stable_hash(input_data), "spend_scope": stable_hash(spend_scope)},
        evidence_refs=["review/paid-scope.json"],
        transaction_id="tx-paid-shot01",
    )
    payload_path = tmp_path / "request.json"
    payload_path.write_text(
        json.dumps(
            {
                "skillId": "image.animate",
                "projectRoot": str(tmp_path),
                "nodeRef": "shot01",
                "input": input_data,
                "approvalRef": approval["approval_id"],
                "transactionId": "tx-paid-shot01",
                "spendScope": spend_scope,
            }
        ),
        encoding="utf-8",
    )

    report = run_skill("image.animate", payload_path)

    assert report["ok"] is True
    assert len(calls) == 1
    receipt = next((tmp_path / "receipts" / "transactions").glob("*.json"))
    saved = json.loads(receipt.read_text())
    assert saved["approval_ref"] == approval["approval_id"]
    assert saved["approval_input_hashes"]["spend_scope"] == stable_hash(spend_scope)


def test_approved_image_animate_uses_real_media_queue_runner(tmp_path: Path) -> None:
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("subtle head turn", encoding="utf-8")
    still = tmp_path / "shot01.png"
    still.write_bytes(b"still")
    input_data = {
        "operation": "image_to_video",
        "promptFile": str(prompt),
        "inputs": [str(still)],
    }
    spend_scope = {
        "shotIds": ["shot01"],
        "candidateCount": 1,
        "budget": {"maxUnits": 1, "currency": "credits"},
    }
    approval = append_approval(
        tmp_path,
        scope="skill:image.animate:shot01",
        approval_type="skill_run",
        approver_type="user",
        approver="dex",
        user_phrase="批准 shot01 入队一个候选，预算一单位",
        input_hashes={"input": stable_hash(input_data), "spend_scope": stable_hash(spend_scope)},
        evidence_refs=["review/paid-scope.json"],
        transaction_id="tx-real-media-queue",
    )
    payload_path = tmp_path / "request.json"
    payload_path.write_text(
        json.dumps(
            {
                "skillId": "image.animate",
                "projectRoot": str(tmp_path),
                "nodeRef": "shot01",
                "input": input_data,
                "approvalRef": approval["approval_id"],
                "transactionId": "tx-real-media-queue",
                "spendScope": spend_scope,
            }
        ),
        encoding="utf-8",
    )

    report = run_skill("image.animate", payload_path)

    assert report["ok"] is True
    queue = json.loads((tmp_path / "receipts" / "media-queue.json").read_text())
    assert len(queue["jobs"]) == 1
    assert queue["jobs"][0]["shot_id"] == "shot01"
    assert queue["jobs"][0]["operation"] == "image_to_video"


def test_director_and_department_skills_expose_typed_operations(tmp_path: Path) -> None:
    director_payload = tmp_path / "director.json"
    director_payload.write_text(
        json.dumps(
            {
                "skillId": "director.control",
                "projectRoot": str(tmp_path),
                "nodeRef": "project",
                "input": {
                    "operation": "rebuild",
                    "changedRefs": ["visual"],
                    "reason": "hair changed",
                    "expectedRevision": 2,
                },
            }
        ),
        encoding="utf-8",
    )
    department_payload = tmp_path / "department.json"
    department_payload.write_text(
        json.dumps(
            {
                "skillId": "department.manage",
                "projectRoot": str(tmp_path),
                "nodeRef": "visual",
                "input": {
                    "operation": "edit",
                    "departmentId": "visual",
                    "payloadFile": str(tmp_path / "edit.json"),
                    "expectedRevision": 3,
                },
            }
        ),
        encoding="utf-8",
    )

    director = run_skill("director.control", director_payload, dry_run=True)
    department = run_skill("department.manage", department_payload, dry_run=True)

    assert director["runner"]["operation"] == "director.rebuild"
    assert director["runner"]["argv"][:2] == ["director", "rebuild"]
    assert department["runner"]["operation"] == "department.edit"
    assert department["runner"]["argv"][:2] == ["department", "edit"]

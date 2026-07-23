from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import skill_runner  # noqa: E402
from skill_runner import RunnerSpec, run_skill  # noqa: E402


def test_same_transaction_reads_receipt_without_duplicate_side_effect(
    tmp_path: Path, monkeypatch
) -> None:
    calls: list[dict[str, object]] = []

    def fake_runner(payload: dict[str, object], _spec: RunnerSpec) -> dict[str, object]:
        calls.append(payload)
        return {"ok": True, "skillId": "dispatch.orchestrate", "nodeRef": "project"}

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
                "transactionId": "tx-user-supplied",
                "input": {},
            }
        ),
        encoding="utf-8",
    )
    first = run_skill("dispatch.orchestrate", payload_path)
    second = run_skill("dispatch.orchestrate", payload_path)
    assert first["transaction_id"] == second["transaction_id"] == "tx-user-supplied"
    assert second["resumed"] is True
    assert first["input_hash"] == second["input_hash"]
    assert first["output_hash"] == second["output_hash"]
    assert first["output_hashes"] == second["output_hashes"]
    assert len(calls) == 1


def test_failed_transaction_is_not_completed_or_replayed_as_success(
    tmp_path: Path, monkeypatch
) -> None:
    calls: list[dict[str, object]] = []

    def fake_runner(payload: dict[str, object], _spec: RunnerSpec) -> dict[str, object]:
        calls.append(payload)
        return {"ok": False, "error": "temporary failure"}

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
                "transactionId": "tx-failed-once",
                "input": {},
            }
        ),
        encoding="utf-8",
    )

    first = run_skill("dispatch.orchestrate", payload_path)
    second = run_skill("dispatch.orchestrate", payload_path)

    assert first["ok"] is False
    assert second["reconciliation_required"] is True
    assert len(calls) == 1
    receipt = json.loads(
        (tmp_path / "receipts" / "transactions" / "tx-failed-once.json").read_text()
    )
    assert receipt["state"] == "failed"

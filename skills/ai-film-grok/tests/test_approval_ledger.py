from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from approval_ledger import (  # noqa: E402
    ApprovalValidationError,
    append_approval,
    approval_is_current,
    read_approval_ledger,
    revoke_approval,
)


def test_records_human_approval_with_exact_hashes_and_stable_id(tmp_path: Path) -> None:
    kwargs = dict(
        scope="pilot:shot01",
        approval_type="pilot",
        approver_type="user",
        approver="dex",
        user_phrase="可以量产",
        input_hashes={"clip": "a" * 64, "scorecard": "b" * 64},
        evidence_refs=["receipts/pilot-scorecard.json"],
        transaction_id="pilot-review-001",
        approved_at="2026-07-23T12:00:00+00:00",
    )
    first = append_approval(tmp_path, **kwargs)
    second = append_approval(tmp_path, **kwargs)

    assert first["approval_id"] == second["approval_id"]
    assert len(read_approval_ledger(tmp_path)["approvals"]) == 1
    assert approval_is_current(first, kwargs["input_hashes"])["ok"]


def test_boolean_or_agent_approval_is_invalid(tmp_path: Path) -> None:
    base = dict(
        scope="final",
        approval_type="final",
        approver="agent",
        input_hashes={"final": "a" * 64},
        evidence_refs=["film_final.mp4"],
        transaction_id="tx-1",
    )
    with pytest.raises(ApprovalValidationError):
        append_approval(tmp_path, approver_type="agent", user_phrase=True, **base)
    with pytest.raises(ApprovalValidationError):
        append_approval(tmp_path, approver_type="human", user_phrase=True, **base)


def test_currentness_reports_exact_changed_and_missing_inputs(tmp_path: Path) -> None:
    approval = append_approval(
        tmp_path,
        scope="story",
        approval_type="creative",
        approver_type="human",
        approver="director",
        authorization_event="review-session-17",
        input_hashes={"story": "a" * 64, "bible": "b" * 64},
        evidence_refs=["review/17.json"],
        transaction_id="tx-17",
    )

    report = approval_is_current(approval, {"story": "c" * 64})

    assert not report["ok"]
    assert report["changed_inputs"] == ["story"]
    assert report["missing_inputs"] == ["bible"]


def test_tampered_ledger_is_rejected(tmp_path: Path) -> None:
    append_approval(
        tmp_path,
        scope="story",
        approval_type="creative",
        approver_type="human",
        approver="director",
        authorization_event="review-session-18",
        input_hashes={"story": "a" * 64},
        evidence_refs=["review/18.json"],
        transaction_id="tx-18",
    )
    path = tmp_path / "receipts" / "approval-ledger.json"
    value = json.loads(path.read_text())
    value["approvals"][0]["scope"] = "stage:bulk"
    path.write_text(json.dumps(value), encoding="utf-8")

    with pytest.raises(ApprovalValidationError, match="tampered"):
        read_approval_ledger(tmp_path)


def test_revoked_approval_is_not_currently_selectable(tmp_path: Path) -> None:
    approval = append_approval(
        tmp_path,
        scope="story",
        approval_type="creative",
        approver_type="human",
        approver="director",
        authorization_event="review-session-19",
        input_hashes={"story": "a" * 64},
        evidence_refs=["review/19.json"],
        transaction_id="tx-19",
    )
    revoke_approval(
        tmp_path,
        approval_id=approval["approval_id"],
        reason="director withdrew approval",
        authorization_event="review-session-20",
        expected_revision=1,
    )

    stored = read_approval_ledger(tmp_path)["approvals"][0]
    assert stored["revoked"] is True


def test_approval_copied_to_another_project_is_not_current(tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    approval = append_approval(
        source,
        scope="stage:pilot_approval",
        approval_type="stage_lock",
        approver_type="human",
        approver="director",
        authorization_event="pilot-screening",
        input_hashes={"pilot": "a" * 64},
        evidence_refs=["review/pilot.json"],
        transaction_id="pilot-approval",
    )
    target_ledger = target / "receipts" / "approval-ledger.json"
    target_ledger.parent.mkdir(parents=True)
    shutil.copyfile(source / "receipts" / "approval-ledger.json", target_ledger)

    copied = read_approval_ledger(target)["approvals"][0]

    assert copied["approval_id"] == approval["approval_id"]
    assert copied["project_binding_current"] is False

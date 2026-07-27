from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from approval_ledger import append_approval  # noqa: E402
from review_control import (  # noqa: E402
    ReviewControlConflict,
    budget_status,
    record_action,
    review_queue,
    update_settings,
)


def _root(tmp_path: Path) -> Path:
    (tmp_path / "receipts").mkdir(parents=True)
    (tmp_path / "drama-graph.json").write_text('{"scenes": []}', encoding="utf-8")
    (tmp_path / "film-spec.json").write_text('{"scenes": []}', encoding="utf-8")
    return tmp_path


def test_queue_marks_approval_stale_when_input_changes(tmp_path: Path) -> None:
    root = _root(tmp_path)
    before = review_queue(root)
    assert before["items"][0]["state"] == "pending_review"
    result = record_action(
        root,
        stage="story",
        action="approve",
        issue="other",
        note="contract checked",
        timestamp_sec=None,
        expected_ledger_revision=before["ledger_revision"],
    )
    assert result["queue"]["items"][0]["state"] == "approved"
    (root / "film-spec.json").write_text('{"scenes": [1]}', encoding="utf-8")
    assert review_queue(root)["items"][0]["state"] == "stale"


def test_reject_records_structured_note_and_checks_revision(tmp_path: Path) -> None:
    root = _root(tmp_path)
    revision = review_queue(root)["ledger_revision"]
    result = record_action(
        root,
        stage="story",
        action="reject",
        issue="story",
        note="missing turn",
        timestamp_sec=2.5,
        expected_ledger_revision=revision,
    )
    assert result["event"]["timestamp_sec"] == 2.5
    with pytest.raises(ReviewControlConflict):
        record_action(
            root,
            stage="story",
            action="reject",
            issue="story",
            note="stale",
            timestamp_sec=None,
            expected_ledger_revision=revision - 1,
        )
    with pytest.raises(ValueError, match="timestamp"):
        record_action(
            root,
            stage="story",
            action="reject",
            issue="story",
            note="invalid timestamp",
            timestamp_sec=float("nan"),
            expected_ledger_revision=revision,
        )


def test_settings_use_optimistic_revision_and_budget_envelopes(tmp_path: Path) -> None:
    root = _root(tmp_path)
    updated = update_settings(
        root, expected_revision=0, reviewer="dex", budget_envelopes={"motion": 12}
    )
    assert updated["budget_envelopes"]["motion"] == 12
    with pytest.raises(ReviewControlConflict):
        update_settings(root, expected_revision=0, reviewer="other")


def test_budget_preserves_unknown_provider_cost(tmp_path: Path) -> None:
    root = _root(tmp_path)
    (root / "receipts" / "generation-usage.json").write_text(
        json.dumps({"events": [{"phase": "accepted", "operation": "i2v", "usage": {}}]}),
        encoding="utf-8",
    )
    assert budget_status(root)["remaining"]["motion"] is None


def test_unbound_or_unsealed_approval_is_never_presented_as_approved(tmp_path: Path) -> None:
    source = _root(tmp_path / "source")
    target = _root(tmp_path / "target")
    item = review_queue(source)["items"][0]
    append_approval(
        source,
        scope="review:story",
        approval_type="review_gate",
        approver_type="human",
        approver="dex",
        authorization_event="review-ui",
        input_hashes=item["input_hashes"],
        evidence_refs=item["evidence_refs"],
        transaction_id="review-ui:story",
    )
    shutil.copyfile(
        source / "receipts" / "approval-ledger.json", target / "receipts" / "approval-ledger.json"
    )
    assert review_queue(target)["items"][0]["state"] == "stale"


def test_queue_rejects_unsafe_manifest_shot_ids(tmp_path: Path) -> None:
    root = _root(tmp_path)
    (root / "manifest.json").write_text(
        json.dumps({"clips": {"');globalThis.pwned=1;//": {}}}), encoding="utf-8"
    )
    assert not any(item["id"].startswith("shot:") for item in review_queue(root)["items"])

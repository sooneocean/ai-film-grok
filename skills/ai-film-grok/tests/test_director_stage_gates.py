from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from approval_ledger import append_approval  # noqa: E402
from director_stage_gates import (  # noqa: E402
    STAGE_ORDER,
    lock_stage,
    stage_status,
)
from production_book import init_production_book  # noqa: E402


def _approve(root: Path, stage: str, hashes: dict[str, str], *, approver_type: str = "human"):
    return append_approval(
        root,
        scope=f"stage:{stage}",
        approval_type="stage_lock",
        approver_type=approver_type,
        approver="director",
        authorization_event=f"review:{stage}",
        input_hashes=hashes,
        evidence_refs=[f"review/{stage}.json"],
        transaction_id=f"tx-{stage}",
    )


def test_professional_stage_order_and_current_human_approval_are_hard(
    tmp_path: Path, monkeypatch
) -> None:
    init_production_book(tmp_path, rigor="professional")
    monkeypatch.setattr(
        "director_cli.validate_native_stage_evidence",
        lambda _root, _stage: {},
    )
    concept = tmp_path / "concept.md"
    concept.write_text("locked concept", encoding="utf-8")
    script = tmp_path / "script.md"
    script.write_text("draft one", encoding="utf-8")

    blocked = stage_status(tmp_path, target_stage="script_lock")
    assert not blocked["ok"]
    assert blocked["blocking"][0]["stage"] == "concept_lock"

    concept_hashes = {"concept": __import__("hashlib").sha256(concept.read_bytes()).hexdigest()}
    concept_approval = _approve(tmp_path, "concept_lock", concept_hashes)
    lock_stage(
        tmp_path,
        stage="concept_lock",
        input_refs={"concept": "concept.md"},
        approval_id=concept_approval["approval_id"],
    )
    script_hashes = {"script.md": __import__("hashlib").sha256(script.read_bytes()).hexdigest()}
    script_approval = _approve(tmp_path, "script_lock", script_hashes)
    lock_stage(
        tmp_path,
        stage="script_lock",
        input_refs={"script.md": "script.md"},
        approval_id=script_approval["approval_id"],
    )

    assert stage_status(tmp_path, target_stage="script_lock")["ok"]
    script.write_text("draft two", encoding="utf-8")
    stale = stage_status(tmp_path, target_stage="script_lock")
    assert not stale["ok"]
    assert any(issue["code"] == "STAGE_INPUT_STALE" for issue in stale["blocking"])


def test_guided_art_locks_are_advisory_but_integrity_locks_block(tmp_path: Path) -> None:
    init_production_book(tmp_path, rigor="guided")

    art = stage_status(tmp_path, target_stage="department_look_lock")
    assert art["ok"]
    assert {item["stage"] for item in art["warnings"]} == {
        "concept_lock",
        "script_lock",
        "department_look_lock",
    }

    integrity = stage_status(tmp_path, target_stage="picture_lock")
    assert not integrity["ok"]
    assert any(item["stage"] == "dailies_review" for item in integrity["blocking"])


def test_legacy_reports_warnings_and_stage_order_is_canonical(tmp_path: Path) -> None:
    init_production_book(tmp_path, rigor="legacy")

    report = stage_status(tmp_path, target_stage="master_lock")

    assert report["ok"]
    assert not report["blocking"]
    assert len(report["warnings"]) == len(STAGE_ORDER)


def test_professional_lock_rejects_arbitrary_file_without_native_stage_evidence(
    tmp_path: Path,
) -> None:
    init_production_book(tmp_path, rigor="professional")
    arbitrary = tmp_path / "looks-valid.json"
    arbitrary.write_text('{"approved":true}\n', encoding="utf-8")
    digest = __import__("hashlib").sha256(arbitrary.read_bytes()).hexdigest()
    approval = _approve(tmp_path, "concept_lock", {"arbitrary": digest})

    with pytest.raises(ValueError, match="native evidence missing"):
        lock_stage(
            tmp_path,
            stage="concept_lock",
            input_refs={"arbitrary": "looks-valid.json"},
            approval_id=approval["approval_id"],
        )

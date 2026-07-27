from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from approval_ledger import append_approval  # noqa: E402
from department_cli import (  # noqa: E402
    DepartmentCliError,
    department_path,
    edit_department,
    handoff_department,
    lock_department,
    migrate_department,
    show_department,
)
from production_book import init_production_book, read_production_book  # noqa: E402


def test_cli_department_edit_dry_run_roundtrip(tmp_path: Path, capsys) -> None:
    from aifilm_grok import main

    init_production_book(tmp_path)
    path = _write_visual(tmp_path)
    before = path.read_bytes()
    payload = tmp_path / "edit.json"
    payload.write_text('{"palette":["amber"]}', encoding="utf-8")
    code = main(
        [
            "department",
            "edit",
            "--root",
            str(tmp_path),
            "--id",
            "visual",
            "--payload-file",
            str(payload),
            "--expected-revision",
            "1",
            "--dry-run",
        ]
    )
    assert code == 0
    assert json.loads(capsys.readouterr().out)["dry_run"] is True
    assert path.read_bytes() == before


def _write_visual(root: Path) -> Path:
    path = root / "style-bible.json"
    path.write_text(
        json.dumps(
            {
                "kind": "visual-bible",
                "revision": 1,
                "state": "review",
                "nodes": {},
            }
        ),
        encoding="utf-8",
    )
    return path


def test_edit_is_atomic_revision_checked_and_supports_dry_run(tmp_path: Path) -> None:
    init_production_book(tmp_path)
    path = _write_visual(tmp_path)
    before = path.read_bytes()
    payload = tmp_path / "edit.json"
    payload.write_text('{"palette":["amber","black"]}', encoding="utf-8")

    preview = edit_department(
        tmp_path, "visual", payload_file=payload, expected_revision=1, dry_run=True
    )
    assert preview["dry_run"] is True
    assert path.read_bytes() == before

    changed = edit_department(
        tmp_path, "visual", payload_file=payload, expected_revision=1, dry_run=False
    )
    assert changed["department"]["revision"] == 2
    assert json.loads(path.read_text())["palette"] == ["amber", "black"]
    with pytest.raises(DepartmentCliError, match="expected revision"):
        edit_department(
            tmp_path, "visual", payload_file=payload, expected_revision=1, dry_run=False
        )


def test_lock_requires_exact_current_human_approval(tmp_path: Path) -> None:
    init_production_book(tmp_path)
    _write_visual(tmp_path)
    with pytest.raises(DepartmentCliError, match="human approval"):
        lock_department(tmp_path, "visual", approval_ref=True, expected_revision=1)  # type: ignore[arg-type]
    with pytest.raises(DepartmentCliError, match="current human approval"):
        lock_department(tmp_path, "visual", approval_ref="approval-missing", expected_revision=1)


def test_lock_rejects_wrong_scope_and_tampered_content(tmp_path: Path) -> None:
    init_production_book(tmp_path)
    path = _write_visual(tmp_path)
    current_hash = show_department(tmp_path, "visual")["department"]["hash"]
    wrong_scope = append_approval(
        tmp_path,
        scope="stage:bulk",
        approval_type="stage_lock",
        approver_type="user",
        approver="dex",
        user_phrase="批准 bulk",
        input_hashes={"department:visual": current_hash},
        evidence_refs=["review/bulk.json"],
        transaction_id="wrong-scope",
    )
    with pytest.raises(DepartmentCliError, match="exact department hash"):
        lock_department(
            tmp_path,
            "visual",
            approval_ref=wrong_scope["approval_id"],
            expected_revision=1,
        )

    approved = append_approval(
        tmp_path,
        scope="department:visual",
        approval_type="department_lock",
        approver_type="user",
        approver="dex",
        user_phrase="批准 visual 定装",
        input_hashes={"department:visual": current_hash},
        evidence_refs=["review/visual.json"],
        transaction_id="visual-lock",
    )
    value = json.loads(path.read_text())
    value["palette"] = ["tampered"]
    value["hash"] = current_hash
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(DepartmentCliError, match="tampered"):
        lock_department(
            tmp_path,
            "visual",
            approval_ref=approved["approval_id"],
            expected_revision=1,
        )


def test_department_lock_updates_production_book(tmp_path: Path) -> None:
    init_production_book(tmp_path)
    _write_visual(tmp_path)
    current_hash = show_department(tmp_path, "visual")["department"]["hash"]
    approval = append_approval(
        tmp_path,
        scope="department:visual",
        approval_type="department_lock",
        approver_type="user",
        approver="dex",
        user_phrase="批准 visual 定装",
        input_hashes={"department:visual": current_hash},
        evidence_refs=["review/visual.json"],
        transaction_id="visual-lock-sync",
    )

    locked = lock_department(
        tmp_path, "visual", approval_ref=approval["approval_id"], expected_revision=1
    )

    book = read_production_book(tmp_path)
    assert locked["department"]["state"] == "locked"
    assert book["departments"]["visual"]["state"] == "locked"
    assert book["departments"]["visual"]["content_sha256"] == locked["department"]["hash"]


def test_unknown_department_cannot_escape_project_root(tmp_path: Path) -> None:
    with pytest.raises(DepartmentCliError, match="unknown department"):
        department_path(tmp_path, "../outside")


def _lock_current_department(root: Path, department: str) -> None:
    current = show_department(root, department)["department"]
    approval = append_approval(
        root,
        scope=f"department:{department}",
        approval_type="department_lock",
        approver_type="user",
        approver="dex",
        user_phrase=f"批准 {department} handoff",
        input_hashes={f"department:{department}": current["hash"]},
        evidence_refs=[f"review/{department}.json"],
        transaction_id=f"{department}-handoff-lock",
    )
    lock_department(
        root,
        department,
        approval_ref=approval["approval_id"],
        expected_revision=current["revision"],
    )


def test_post_handoff_requires_locked_visual_and_audio_bibles(tmp_path: Path) -> None:
    init_production_book(tmp_path)
    _write_visual(tmp_path)
    (tmp_path / "audio-bible.json").write_text("{}", encoding="utf-8")
    migrate_department(tmp_path, "audio")

    blocked = handoff_department(tmp_path, "post")
    assert blocked["ok"] is False
    assert blocked["owner"] == "post"
    assert blocked["blocked_by"] == [
        {"id": "visual", "reason": "state_review"},
        {"id": "audio", "reason": "state_draft"},
    ]

    _lock_current_department(tmp_path, "visual")
    _lock_current_department(tmp_path, "audio")
    ready = handoff_department(tmp_path, "post")

    assert ready["ok"] is True
    assert ready["blocked_by"] == []
    assert {item["id"] for item in ready["inputs"]} == {"visual", "audio"}
    assert all(item["state"] == "locked" for item in ready["inputs"])
    assert ready["handoff_id"].startswith("department-handoff-post-")


def test_handoff_cli_reports_nonzero_when_upstream_is_not_locked(tmp_path: Path, capsys) -> None:
    from aifilm_grok import main

    init_production_book(tmp_path)
    _write_visual(tmp_path)
    (tmp_path / "audio-bible.json").write_text("{}", encoding="utf-8")
    migrate_department(tmp_path, "audio")

    code = main(["department", "handoff", "--root", str(tmp_path), "--to", "post"])

    assert code == 1
    report = json.loads(capsys.readouterr().out)
    assert report["ok"] is False
    assert report["to"] == "post"


def test_post_handoff_rejects_a_locked_bible_without_current_approval(tmp_path: Path) -> None:
    init_production_book(tmp_path)
    _write_visual(tmp_path)
    (tmp_path / "audio-bible.json").write_text("{}", encoding="utf-8")
    migrate_department(tmp_path, "audio")
    _lock_current_department(tmp_path, "visual")
    _lock_current_department(tmp_path, "audio")

    visual_path = tmp_path / "style-bible.json"
    visual = json.loads(visual_path.read_text(encoding="utf-8"))
    visual["approval_ref"] = "approval-for-another-department"
    visual_path.write_text(json.dumps(visual), encoding="utf-8")

    report = handoff_department(tmp_path, "post")

    assert report["ok"] is False
    assert report["blocked_by"] == [{"id": "visual", "reason": "approval_not_current"}]


def test_concurrent_edits_cannot_both_commit_same_expected_revision(tmp_path: Path) -> None:
    init_production_book(tmp_path)
    _write_visual(tmp_path)
    payloads = []
    for marker in ("A", "B"):
        path = tmp_path / f"edit-{marker}.json"
        path.write_text(json.dumps({"marker": marker}), encoding="utf-8")
        payloads.append(path)

    def edit(path: Path):
        return edit_department(
            tmp_path,
            "visual",
            payload_file=path,
            expected_revision=1,
            dry_run=False,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(edit, path) for path in payloads]
    outcomes = []
    for future in futures:
        try:
            outcomes.append(future.result()["ok"])
        except DepartmentCliError:
            outcomes.append(False)

    assert sorted(outcomes) == [False, True]
    bible = show_department(tmp_path, "visual")["department"]
    book = read_production_book(tmp_path)
    assert book["departments"]["visual"]["content_sha256"] == bible["hash"]

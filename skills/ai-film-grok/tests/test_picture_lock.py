from __future__ import annotations

import hashlib
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from approval_ledger import append_approval  # noqa: E402
from picture_lock import (  # noqa: E402
    bind_picture_lock,
    picture_lock_inputs,
    picture_lock_status,
)


def test_picture_lock_binds_exact_timeline_edl_and_ordered_shot_set(tmp_path: Path) -> None:
    (tmp_path / "edit").mkdir()
    (tmp_path / "edit" / "cut.edl").write_text("EDL v1", encoding="utf-8")
    (tmp_path / "edit" / "timeline.json").write_text('{"v":1}', encoding="utf-8")
    refs = {"edl": "edit/cut.edl", "timeline": "edit/timeline.json"}
    hashes = picture_lock_inputs(tmp_path, refs, ["shot-001", "shot-002"])
    approval = append_approval(
        tmp_path,
        scope="stage:picture_lock",
        approval_type="stage_lock",
        approver_type="human",
        approver="editor",
        authorization_event="screening-12",
        input_hashes=hashes,
        evidence_refs=["review/screening-12.json"],
        transaction_id="picture-12",
    )

    bind_picture_lock(
        tmp_path,
        input_refs=refs,
        shot_ids=["shot-001", "shot-002"],
        approval_id=approval["approval_id"],
    )

    assert picture_lock_status(tmp_path)["ok"]
    changed_ids = picture_lock_status(tmp_path, current_shot_ids=["shot-003", "shot-004"])
    assert not changed_ids["ok"]
    assert changed_ids["shot_set"]["same_count"]
    assert changed_ids["shot_set"]["changed"]


def test_edl_change_precisely_stales_post_locks_without_deleting_assets(tmp_path: Path) -> None:
    (tmp_path / "cut.edl").write_text("v1", encoding="utf-8")
    refs = {"edl": "cut.edl"}
    hashes = picture_lock_inputs(tmp_path, refs, ["shot-a"])
    approval = append_approval(
        tmp_path,
        scope="stage:picture_lock",
        approval_type="stage_lock",
        approver_type="user",
        approver="dex",
        user_phrase="picture lock",
        input_hashes=hashes,
        evidence_refs=["cut.edl"],
        transaction_id="pl-1",
    )
    bind_picture_lock(
        tmp_path,
        input_refs=refs,
        shot_ids=["shot-a"],
        approval_id=approval["approval_id"],
    )
    (tmp_path / "cut.edl").write_text("v2", encoding="utf-8")

    report = picture_lock_status(tmp_path)

    assert not report["ok"]
    assert report["changed_inputs"] == ["edl"]
    assert report["affected_locks"] == ["sound", "music", "captions", "mix", "master"]
    assert report["assets_deleted"] == []
    assert hashlib.sha256((tmp_path / "cut.edl").read_bytes()).hexdigest() != hashes["edl"]


def test_explicit_empty_current_shot_set_invalidates_lock(tmp_path: Path) -> None:
    (tmp_path / "cut.edl").write_text("v1", encoding="utf-8")
    refs = {"edl": "cut.edl"}
    hashes = picture_lock_inputs(tmp_path, refs, ["shot-a"])
    approval = append_approval(
        tmp_path,
        scope="stage:picture_lock",
        approval_type="stage_lock",
        approver_type="user",
        approver="dex",
        user_phrase="picture lock",
        input_hashes=hashes,
        evidence_refs=["cut.edl"],
        transaction_id="pl-empty",
    )
    bind_picture_lock(
        tmp_path,
        input_refs=refs,
        shot_ids=["shot-a"],
        approval_id=approval["approval_id"],
    )

    status = picture_lock_status(tmp_path, current_shot_ids=[])

    assert status["ok"] is False
    assert status["shot_set"]["changed"] is True
    assert status["shot_set"]["current_ids"] == []

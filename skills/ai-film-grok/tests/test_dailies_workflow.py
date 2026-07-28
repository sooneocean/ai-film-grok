from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from dailies import dailies_review_status, dailies_status, update_dailies  # noqa: E402
from director_cli import validate_native_stage_evidence  # noqa: E402
from selects_report import build_selects_report  # noqa: E402
from workflow_spine import _selects_current  # noqa: E402


def _project(root: Path, shot_ids: tuple[str, ...] = ("s001",)) -> dict[str, Path]:
    clips: dict[str, dict[str, str]] = {}
    paths: dict[str, Path] = {}
    for shot_id in shot_ids:
        path = root / "clips" / f"{shot_id}.mp4"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"clip:{shot_id}".encode())
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        paths[shot_id] = path
        clips[shot_id] = {"path": str(path), "sha256": digest, "status": "approved"}
    (root / "film-spec.json").write_text(
        json.dumps({"shots": [{"id": shot_id} for shot_id in shot_ids]}),
        encoding="utf-8",
    )
    (root / "manifest.json").write_text(json.dumps({"clips": clips}), encoding="utf-8")
    return paths


def test_canonical_dailies_requires_exactly_one_select_per_planned_shot(
    tmp_path: Path,
) -> None:
    paths = _project(tmp_path)
    alternate = tmp_path / "clips" / "s001-alt.mp4"
    alternate.write_bytes(b"alternate")
    for reviewer, candidate in (("a", paths["s001"]), ("b", alternate)):
        update_dailies(
            tmp_path,
            shot_id="s001",
            candidate=str(candidate),
            status="select",
            reviewer=reviewer,
            notes="chosen",
        )

    status = dailies_status(tmp_path)

    assert status["ok"] is False
    assert {item["code"] for item in status["issues"]} == {"DAILIES_SELECT_COUNT"}


def test_selects_projection_rejects_unclassified_reject_and_stale_media(
    tmp_path: Path,
) -> None:
    paths = _project(tmp_path, ("s001", "s002"))
    update_dailies(
        tmp_path,
        shot_id="s001",
        candidate=str(paths["s001"]),
        status="select",
        reviewer="director",
        notes="chosen",
    )
    update_dailies(
        tmp_path,
        shot_id="s002",
        candidate=str(paths["s002"]),
        status="reject",
        reviewer="director",
        notes="",
    )
    paths["s001"].write_bytes(b"replacement")

    report = build_selects_report(tmp_path, write_receipt=False)

    assert report["complete"] is False
    codes = {item["code"] for item in dailies_status(tmp_path)["issues"]}
    assert "DAILIES_REJECT_REASON_MISSING" in codes
    assert "DAILIES_MEDIA_STALE" in codes


def test_selects_projection_binds_select_hash_to_approved_manifest(
    tmp_path: Path,
) -> None:
    paths = _project(tmp_path, ("s001", "s002"))
    for shot_id in ("s001", "s002"):
        update_dailies(
            tmp_path,
            shot_id=shot_id,
            candidate=str(paths[shot_id]),
            status="select",
            reviewer="director",
            notes="chosen",
        )

    report = build_selects_report(tmp_path, write_receipt=False)

    assert report["complete"] is True
    assert report["canonical_ledger"] == "receipts/dailies.json"
    assert report["selected_set_sha256"]


def test_dailies_review_can_complete_before_any_take_is_selected(tmp_path: Path) -> None:
    paths = _project(tmp_path)
    update_dailies(
        tmp_path,
        shot_id="s001",
        candidate=str(paths["s001"]),
        status="alternate",
        reviewer="director",
        notes="hold for selects",
    )

    assert dailies_review_status(tmp_path)["ok"] is True
    assert dailies_status(tmp_path)["ok"] is False


def test_live_selects_projection_invalidates_stale_written_receipt(tmp_path: Path) -> None:
    paths = _project(tmp_path)
    update_dailies(
        tmp_path,
        shot_id="s001",
        candidate=str(paths["s001"]),
        status="select",
        reviewer="director",
        notes="chosen",
    )
    assert build_selects_report(tmp_path, write_receipt=True)["complete"] is True

    paths["s001"].write_bytes(b"replacement")

    assert _selects_current(tmp_path) is False


def test_nested_scene_shots_drive_dailies_and_selects(tmp_path: Path) -> None:
    paths = _project(tmp_path)
    (tmp_path / "film-spec.json").write_text(
        json.dumps({"scenes": [{"id": "scene-1", "shots": [{"id": "s001"}]}]}),
        encoding="utf-8",
    )
    update_dailies(
        tmp_path,
        shot_id="s001",
        candidate=str(paths["s001"]),
        status="select",
        reviewer="director",
        notes="chosen",
    )

    assert dailies_review_status(tmp_path)["planned_shot_ids"] == ["s001"]
    assert build_selects_report(tmp_path, write_receipt=False)["complete"] is True


def test_relative_candidate_can_be_reclassified_without_spending_more_budget(
    tmp_path: Path,
) -> None:
    _project(tmp_path)
    update_dailies(
        tmp_path,
        shot_id="s001",
        candidate="clips/s001.mp4",
        status="alternate",
        reviewer="director",
        notes="hold",
        approved_budget=1,
    )
    update_dailies(
        tmp_path,
        shot_id="s001",
        candidate="clips/s001.mp4",
        status="select",
        reviewer="director",
        notes="chosen",
        approved_budget=1,
    )

    assert dailies_status(tmp_path)["ok"] is True
    second = tmp_path / "clips" / "s001-alt.mp4"
    second.write_bytes(b"alternate")
    with pytest.raises(ValueError, match="budget exhausted"):
        update_dailies(
            tmp_path,
            shot_id="s001",
            candidate="clips/s001-alt.mp4",
            status="alternate",
            reviewer="director",
            notes="new take",
            approved_budget=1,
        )
    assert dailies_status(tmp_path)["selections"][0]["candidate"] == str(
        tmp_path / "clips" / "s001.mp4"
    )


@pytest.mark.parametrize(("stale_selects", "stale_rough"), [(True, False), (False, True)])
def test_selects_stage_rejects_receipts_not_bound_to_live_selected_set(
    tmp_path: Path,
    stale_selects: bool,
    stale_rough: bool,
) -> None:
    paths = _project(tmp_path)
    update_dailies(
        tmp_path,
        shot_id="s001",
        candidate=str(paths["s001"]),
        status="select",
        reviewer="director",
        notes="chosen",
    )
    report = build_selects_report(tmp_path, write_receipt=True)
    current_hash = report["selected_set_sha256"]
    stored = {
        **report,
        "selected_set_sha256": "stale" if stale_selects else current_hash,
    }
    receipts = tmp_path / "receipts"
    (receipts / "selects-report.json").write_text(json.dumps(stored), encoding="utf-8")
    (receipts / "rough-cut.json").write_text(
        json.dumps(
            {
                "ok": True,
                "selected_set_sha256": "stale" if stale_rough else current_hash,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="ordered selected take set"):
        validate_native_stage_evidence(tmp_path, "selects_rough_cut")


def test_selects_stage_accepts_receipts_bound_to_live_selected_set(tmp_path: Path) -> None:
    paths = _project(tmp_path)
    update_dailies(
        tmp_path,
        shot_id="s001",
        candidate=str(paths["s001"]),
        status="select",
        reviewer="director",
        notes="chosen",
    )
    report = build_selects_report(tmp_path, write_receipt=True)
    (tmp_path / "receipts" / "rough-cut.json").write_text(
        json.dumps({"ok": True, "selected_set_sha256": report["selected_set_sha256"]}),
        encoding="utf-8",
    )

    assert validate_native_stage_evidence(tmp_path, "selects_rough_cut")["rough"] == (
        "receipts/rough-cut.json"
    )

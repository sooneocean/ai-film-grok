from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from dailies import dailies_status, update_dailies  # noqa: E402
from selects_report import build_selects_report  # noqa: E402


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
    for reviewer in ("a", "b"):
        update_dailies(
            tmp_path,
            shot_id="s001",
            candidate=str(paths["s001"]),
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

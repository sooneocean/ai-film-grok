from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from prompt_injector import PromptInjector  # noqa: E402
from state_index_gate import run_state_index_check  # noqa: E402
from visual_bible import resolve_state_photo  # noqa: E402
from wardrobe_ladder import approve_state, ensure_ladder, ladder_plan  # noqa: E402


def _write_image(root: Path, relative: str, content: bytes) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _ladder(root: Path, *, approved: bool) -> dict:
    states = []
    for index, (state_id, category) in enumerate(
        [("full", "full"), ("coat-off", "partial"), ("top-off", "undressed")]
    ):
        path = f"canonical/cast-states/hero/{state_id}.png"
        image = _write_image(root, path, f"image-{state_id}".encode())
        state = {
            "id": state_id,
            "parent_state_id": None if index == 0 else states[index - 1]["id"],
            "removed_garment_ids": ["coat", "top"][:index],
            "wardrobe_state": category,
            "path": path,
            "status": "approved" if approved else "pending",
        }
        if approved:
            state["sha256"] = hashlib.sha256(image.read_bytes()).hexdigest()
        states.append(state)
    return {"hero": {"garments": [{"id": "coat"}, {"id": "top"}], "states": states}}


def _spec(state_id: str | None = None) -> dict:
    shot = {
        "id": "shot01",
        "heroine_ids": ["hero"],
        "wardrobe_state": "undressed",
        "dsl": {"wardrobe_state": "undressed"},
    }
    if state_id:
        shot["wardrobe_state_id"] = state_id
    return {"heat_scale": "standard", "scenes": [{"shots": [shot]}]}


def test_ladder_plan_is_serial_and_removes_one_garment_per_step(tmp_path: Path) -> None:
    bible = {"wardrobe_ladders": _ladder(tmp_path, approved=False)}
    issues, plan = ladder_plan(bible, "hero", root=tmp_path)

    assert any(issue["code"] == "WARDROBE_FULL_STATE_UNAPPROVED" for issue in issues)
    assert [item["remove_garment_id"] for item in plan] == ["coat", "top"]
    assert [item["parent_state_id"] for item in plan] == ["full", "coat-off"]


def test_explicit_garments_auto_expand_into_serial_state_chain(tmp_path: Path) -> None:
    bible = {
        "cast_masters": {"hero": "canonical/cast/hero.png"},
        "wardrobe_ladders": {"hero": {"garments": [{"id": "coat"}, {"id": "top"}]}},
    }
    ladder = ensure_ladder(bible, "hero", {"full", "undressed"}, root=tmp_path)

    assert ladder is not None
    assert [state["id"] for state in ladder["states"]] == ["full", "remove-coat", "remove-top"]
    assert ladder["states"][-1]["wardrobe_state"] == "undressed"
    _, plan = ladder_plan(bible, "hero", root=tmp_path)
    assert [step["parent_state_id"] for step in plan] == ["full", "remove-coat"]


def test_exact_state_photo_is_primary_and_receipt_records_lineage(tmp_path: Path) -> None:
    bible = {"wardrobe_ladders": _ladder(tmp_path, approved=True), "characters": {"hero": {}}}
    exact = resolve_state_photo(
        bible, "hero", "undressed", root=tmp_path, wardrobe_state_id="top-off"
    )
    assert exact == "canonical/cast-states/hero/top-off.png"

    receipt = PromptInjector(bible).assemble(
        {
            "id": "shot01",
            "heroine_ids": ["hero"],
            "wardrobe_state": "undressed",
            "wardrobe_state_id": "top-off",
            "dsl": {},
        },
        tmp_path,
    )
    assert receipt["state_photo_primary"] == exact
    assert receipt["state_photo_records"][0]["parent_state_id"] == "coat-off"
    assert receipt["state_photo_records"][0]["removed_garment_ids"] == ["coat", "top"]


def test_state_index_blocks_missing_or_drifted_ladder_states(tmp_path: Path) -> None:
    bible = {"wardrobe_ladders": _ladder(tmp_path, approved=True)}
    (tmp_path / "style-bible.json").write_text(json.dumps(bible), encoding="utf-8")
    (tmp_path / "film-spec.json").write_text(json.dumps(_spec("top-off")), encoding="utf-8")
    report = run_state_index_check(tmp_path)
    assert report["ok"], report

    (tmp_path / "canonical/cast-states/hero/top-off.png").write_bytes(b"drift")
    report = run_state_index_check(tmp_path)
    assert not report["ok"]
    assert "WARDROBE_STATE_HASH_DRIFT" in {issue["code"] for issue in report["hard"]}


def test_approve_state_requires_approved_parent(tmp_path: Path) -> None:
    bible = {"wardrobe_ladders": _ladder(tmp_path, approved=False)}
    with pytest.raises(ValueError, match="parent state full"):
        approve_state(
            bible,
            "hero",
            "coat-off",
            tmp_path / "canonical/cast-states/hero/coat-off.png",
            root=tmp_path,
        )

    approve_state(
        bible, "hero", "full", tmp_path / "canonical/cast-states/hero/full.png", root=tmp_path
    )
    state = approve_state(
        bible,
        "hero",
        "coat-off",
        tmp_path / "canonical/cast-states/hero/coat-off.png",
        root=tmp_path,
    )
    assert state["status"] == "approved"

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest
from PIL import Image

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from prompt_injector import PromptInjector  # noqa: E402
from state_index_gate import run_state_index_check  # noqa: E402
from visual_bible import resolve_state_photo  # noqa: E402
from wardrobe_ladder import (  # noqa: E402
    approve_state,
    ensure_ladder,
    ladder_plan,
    render_contact_sheet,
)


def _write_image(root: Path, relative: str, content: bytes) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    color = tuple(content[:3].ljust(3, b"\0"))
    Image.new("RGB", (64, 96), color).save(path, format="PNG")
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
    assert plan == []
    assert any(issue["code"] == "WARDROBE_LADDER_PARENT_UNAPPROVED" for issue in issues)

    full = bible["wardrobe_ladders"]["hero"]["states"][0]
    full_path = tmp_path / full["path"]
    full.update(status="approved", sha256=hashlib.sha256(full_path.read_bytes()).hexdigest())
    _, plan = ladder_plan(bible, "hero", root=tmp_path)
    assert [item["remove_garment_id"] for item in plan] == ["coat"]
    assert [item["parent_state_id"] for item in plan] == ["full"]


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
    assert plan == []


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


def test_active_ladder_plan_never_includes_legacy_full_restart_task(tmp_path: Path) -> None:
    bible = {"wardrobe_ladders": _ladder(tmp_path, approved=False)}
    approve_state(
        bible,
        "hero",
        "full",
        tmp_path / "canonical/cast-states/hero/full.png",
        root=tmp_path,
        reviewer="qa",
        review_note="full look checked",
    )
    (tmp_path / "style-bible.json").write_text(json.dumps(bible), encoding="utf-8")
    (tmp_path / "film-spec.json").write_text(json.dumps(_spec("top-off")), encoding="utf-8")

    report = run_state_index_check(tmp_path)
    actions = {item["action"] for item in report["generate_plan"]}

    assert "generate_wardrobe_state_photo" in actions
    assert "generate_state_photo" not in actions


def test_nonfull_story_without_ladder_stops_at_breakdown_not_legacy_edit(tmp_path: Path) -> None:
    (tmp_path / "style-bible.json").write_text("{}", encoding="utf-8")
    (tmp_path / "film-spec.json").write_text(json.dumps(_spec()), encoding="utf-8")

    report = run_state_index_check(tmp_path)

    assert "MISSING_WARDROBE_LADDER" in {issue["code"] for issue in report["hard"]}
    assert "generate_state_photo" not in {item["action"] for item in report["generate_plan"]}


def test_full_only_cast_member_does_not_require_another_characters_ladder(tmp_path: Path) -> None:
    bible = {"wardrobe_ladders": _ladder(tmp_path, approved=True)}
    spec = _spec("top-off")
    spec["scenes"][0]["shots"].append(
        {
            "id": "shot02",
            "heroine_ids": ["support"],
            "wardrobe_state": "full",
            "dsl": {"wardrobe_state": "full"},
        }
    )
    (tmp_path / "style-bible.json").write_text(json.dumps(bible), encoding="utf-8")
    (tmp_path / "film-spec.json").write_text(json.dumps(spec), encoding="utf-8")

    report = run_state_index_check(tmp_path)
    codes = {issue["code"] for issue in report["hard"]}

    assert "MISSING_WARDROBE_LADDER" not in codes


def test_exact_state_never_falls_back_to_another_characters_hero_state(tmp_path: Path) -> None:
    hero_ladder = _ladder(tmp_path, approved=True)
    villain_ladder = _ladder(tmp_path, approved=True)
    old_to_new = {"full": "v-full", "coat-off": "v-coat-off", "top-off": "v-top-off"}
    for state in villain_ladder["hero"]["states"]:
        old_id = state["id"]
        state["id"] = old_to_new[old_id]
        if state["parent_state_id"]:
            state["parent_state_id"] = old_to_new[state["parent_state_id"]]
        state["path"] = state["path"].replace("hero/", "villain/")
        image = _write_image(tmp_path, state["path"], f"villain-{old_id}".encode())
        state["sha256"] = hashlib.sha256(image.read_bytes()).hexdigest()
    villain_ladder["villain"] = villain_ladder.pop("hero")
    bible = {"wardrobe_ladders": {**hero_ladder, **villain_ladder}}

    assert (
        resolve_state_photo(
            bible, "villain", "undressed", root=tmp_path, wardrobe_state_id="top-off"
        )
        is None
    )


def test_enabled_ladder_requires_exact_state_id_for_non_full_shot(tmp_path: Path) -> None:
    bible = {"wardrobe_ladders": _ladder(tmp_path, approved=True)}
    (tmp_path / "style-bible.json").write_text(json.dumps(bible), encoding="utf-8")
    (tmp_path / "film-spec.json").write_text(json.dumps(_spec()), encoding="utf-8")

    report = run_state_index_check(tmp_path)
    assert not report["ok"]
    assert "WARDROBE_STATE_ID_REQUIRED" in {issue["code"] for issue in report["hard"]}


def test_exact_state_must_match_the_shots_wardrobe_category(tmp_path: Path) -> None:
    bible = {"wardrobe_ladders": _ladder(tmp_path, approved=True)}
    (tmp_path / "style-bible.json").write_text(json.dumps(bible), encoding="utf-8")
    (tmp_path / "film-spec.json").write_text(json.dumps(_spec("full")), encoding="utf-8")

    report = run_state_index_check(tmp_path)
    assert not report["ok"]
    assert "WARDROBE_STATE_ID_MISMATCH" in {issue["code"] for issue in report["hard"]}


def test_approve_state_requires_approved_parent(tmp_path: Path) -> None:
    bible = {"wardrobe_ladders": _ladder(tmp_path, approved=False)}
    with pytest.raises(ValueError, match="parent state full"):
        approve_state(
            bible,
            "hero",
            "coat-off",
            tmp_path / "canonical/cast-states/hero/coat-off.png",
            root=tmp_path,
            reviewer="qa",
            review_note="checked",
        )

    approve_state(
        bible,
        "hero",
        "full",
        tmp_path / "canonical/cast-states/hero/full.png",
        root=tmp_path,
        reviewer="qa",
        review_note="full look checked",
    )
    receipt = tmp_path / "receipts" / "coat-off.json"
    receipt.parent.mkdir()
    receipt.write_text(
        json.dumps(
            {
                "kind": "image_edit",
                "parent_state_id": "full",
                "parent_state_sha256": bible["wardrobe_ladders"]["hero"]["states"][0]["sha256"],
                "output_sha256": hashlib.sha256(
                    (tmp_path / "canonical/cast-states/hero/coat-off.png").read_bytes()
                ).hexdigest(),
            }
        ),
        encoding="utf-8",
    )
    state = approve_state(
        bible,
        "hero",
        "coat-off",
        tmp_path / "canonical/cast-states/hero/coat-off.png",
        root=tmp_path,
        reviewer="qa",
        review_note="coat only removed",
        generation_receipt=receipt,
    )
    assert state["status"] == "approved"
    assert state["approval"]["parent"]["state_id"] == "full"
    assert state["approval"]["image"]["width"] == 64
    assert state["generation_receipt"]["path"] == "receipts/coat-off.json"


def test_nonfull_approval_requires_review_and_i2i_receipt(tmp_path: Path) -> None:
    bible = {"wardrobe_ladders": _ladder(tmp_path, approved=False)}
    approve_state(
        bible,
        "hero",
        "full",
        tmp_path / "canonical/cast-states/hero/full.png",
        root=tmp_path,
        reviewer="qa",
        review_note="full checked",
    )
    with pytest.raises(ValueError, match="generation_receipt"):
        approve_state(
            bible,
            "hero",
            "coat-off",
            tmp_path / "canonical/cast-states/hero/coat-off.png",
            root=tmp_path,
            reviewer="qa",
            review_note="coat removed",
        )


def test_nonfull_approval_rejects_unbound_receipt_or_drifted_parent(tmp_path: Path) -> None:
    bible = {"wardrobe_ladders": _ladder(tmp_path, approved=False)}
    approve_state(
        bible,
        "hero",
        "full",
        tmp_path / "canonical/cast-states/hero/full.png",
        root=tmp_path,
        reviewer="qa",
        review_note="full checked",
    )
    bogus = tmp_path / "receipts" / "bogus.json"
    bogus.parent.mkdir()
    bogus.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="must bind image_edit"):
        approve_state(
            bible,
            "hero",
            "coat-off",
            tmp_path / "canonical/cast-states/hero/coat-off.png",
            root=tmp_path,
            reviewer="qa",
            review_note="coat removed",
            generation_receipt=bogus,
        )

    (tmp_path / "canonical/cast-states/hero/full.png").write_bytes(b"drift")
    with pytest.raises(ValueError, match="missing or hash-drifted"):
        approve_state(
            bible,
            "hero",
            "coat-off",
            tmp_path / "canonical/cast-states/hero/coat-off.png",
            root=tmp_path,
            reviewer="qa",
            review_note="coat removed",
            generation_receipt=bogus,
        )
    with pytest.raises(ValueError, match="reviewer and review_note"):
        approve_state(
            bible,
            "hero",
            "full",
            tmp_path / "canonical/cast-states/hero/full.png",
            root=tmp_path,
            reviewer="",
            review_note="",
        )


def test_contact_sheet_shows_every_ladder_state(tmp_path: Path) -> None:
    bible = {"wardrobe_ladders": _ladder(tmp_path, approved=True)}
    result = render_contact_sheet(bible, "hero", root=tmp_path)
    image = Image.open(tmp_path / result["path"])

    assert image.width == 720
    assert len(result["states"]) == 3
    assert result["states"][-1]["removed_garment_ids"] == ["coat", "top"]


def test_wardrobe_schemas_declare_exact_ladder_and_binding() -> None:
    schemas = Path(__file__).resolve().parents[1] / "schemas"
    bible_schema = json.loads((schemas / "style-bible.schema.json").read_text(encoding="utf-8"))
    binding_schema = json.loads(
        (schemas / "wardrobe-state-binding.schema.json").read_text(encoding="utf-8")
    )

    ladder = bible_schema["properties"]["wardrobe_ladders"]
    assert ladder["additionalProperties"]["required"] == ["garments", "states"]
    assert binding_schema["required"] == ["wardrobe_state_id"]
    assert "undressed" in binding_schema["properties"]["wardrobe_state"]["enum"]

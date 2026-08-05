"""Weapon inventory SSoT: tiers, primaries, routing + handoff consistency."""

from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from comfy_armory import select_weapon  # noqa: E402
from generation_request import build_generation_request  # noqa: E402
from weapon_inventory import (  # noqa: E402
    inventory_path,
    inventory_summary_line,
    load_inventory,
    primaries,
    primary_for,
    primary_weapon_id_for_router_operation,
    validate_inventory,
)
from weapon_router import build_weapon_route  # noqa: E402


def test_inventory_file_exists_and_loads() -> None:
    assert inventory_path().is_file()
    data = load_inventory()
    assert data["ok"] is True
    assert data["kind"] == "ai-film-weapon-inventory"
    for modality in ("text", "still", "motion", "audio"):
        assert modality in data["modalities"]
        entries = data["modalities"][modality]["entries"]
        assert entries
        tiers = {e.get("tier") for e in entries}
        assert "primary" in tiers, f"{modality} missing primary"


def test_validate_inventory_green() -> None:
    report = validate_inventory()
    assert report["ok"] is True, report.get("errors")
    assert report["primary_count"] >= 8
    assert set(report["modalities"]) == {"text", "still", "motion", "audio"}


def test_every_primary_has_tier_and_why() -> None:
    for entry in primaries():
        assert entry.get("id")
        assert entry.get("tier") == "primary"
        assert entry.get("modality") in {"text", "still", "motion", "audio"}
        assert entry.get("why") or entry.get("demand_classes")


def test_still_t2i_primary_matches_select_weapon() -> None:
    inv = primary_for("text-to-image")
    assert inv and inv["id"] == "qwen-image-2512-quality"
    selected = select_weapon("text-to-image", stage="production")
    assert selected["weapon"]["id"] == primary_weapon_id_for_router_operation("text-to-image")
    assert selected["weapon"]["id"] == "qwen-image-2512-quality"
    assert selected["weapon"]["verified"].get("production_promoted") is True


def test_still_edit_primary_matches_select_weapon() -> None:
    inv = primary_for("local-image-edit")
    assert inv and inv["id"] == "qwen-image-edit-2511-local"
    selected = select_weapon("image-edit", identity_lock=True, stage="production")
    assert selected["weapon"]["id"] == "qwen-image-edit-2511-local"
    assert selected["weapon"]["verified"].get("production_promoted") is True


def test_motion_i2v_primary_matches_select_weapon_and_router(tmp_path: Path) -> None:
    inv = primary_for("image-to-video")
    assert inv and inv["registry_weapon"] == "minimax-h3-i2v-pilot"
    selected = select_weapon("image-to-video", stage="production")
    assert selected["weapon"]["id"] == "minimax-h3-i2v-pilot"
    assert selected["weapon"]["verified"]["production_promoted"] is True

    route = build_weapon_route(
        tmp_path,
        workflow={"mode": "professional", "current_stage": "bulk"},
        primary_job={"skillId": "image.animate"},
    )
    assert route["status"] == "ready"
    assert route["weapon_id"] == "minimax-h3-i2v-pilot"
    assert route["provider"] == "comfy-h3"
    assert route["production_promoted"] is True


def test_still_demand_router_uses_inventory_t2i_primary(tmp_path: Path) -> None:
    route = build_weapon_route(
        tmp_path,
        workflow={"mode": "professional", "current_stage": "shot_animatic_lock"},
    )
    assert route["status"] == "ready"
    assert route["weapon_id"] == primary_weapon_id_for_router_operation("text-to-image")
    assert route["weapon_id"] == "qwen-image-2512-quality"


def test_audio_and_text_primaries_documented() -> None:
    assert primary_for("tts_zh_ship")["id"] == "edge_tts_zh"
    assert primary_for("chinese_vo")["id"] == "edge_tts_zh"
    assert primary_for("bgm")["id"] == "bgm_recipe_rnb"
    assert primary_for("motion_prompt")["id"] == "motion_prompt_spine"
    assert primary_for("still_prompt")["id"] == "prompt_injector"


def test_no_orphan_primary_names() -> None:
    report = validate_inventory()
    assert not any("orphan" in e for e in report.get("errors") or []), report


def test_generation_request_handoff_has_sha(tmp_path: Path) -> None:
    root = tmp_path / "film"
    root.mkdir()
    still = root / "stills" / "s01.png"
    still.parent.mkdir(parents=True)
    still.write_bytes(b"\x89PNG\r\n\x1a\n" + b"H" * 40)
    (root / "film-spec.json").write_text(
        json.dumps(
            {
                "title": "inv-handoff",
                "director_intent": {
                    "logline": "t",
                    "theme": "t",
                    "protagonist_want": "escape",
                },
                "scenes": [
                    {
                        "id": "sc1",
                        "shots": [
                            {
                                "id": "s01",
                                "wardrobe_state": "full",
                                "dramatic_function": "hook",
                                "visible_change": "steps forward",
                                "dsl": {
                                    "action": "steps",
                                    "motion": "walk two steps",
                                    "camera": {"shot_size": "ms"},
                                },
                                "duration_sec": 4,
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (root / "manifest.json").write_text(
        json.dumps({"stills": {"s01": {"path": str(still), "status": "approved"}}}),
        encoding="utf-8",
    )
    (root / "style-bible.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "signature_block": "cel anime",
                "medium": "anime",
                "style_fingerprint": {"medium_key": "anime"},
            }
        ),
        encoding="utf-8",
    )
    req = build_generation_request(root, "s01", kind="i2v", write=True)
    assert req["kind"] == "generation-request"
    assert req["text_sha256"]
    assert len(req["text_sha256"]) == 64
    assert req["image_refs"]
    first = req["image_refs"][0]
    assert first.get("path")
    assert first.get("sha256")
    assert first.get("role") in {"first", "state_photo"}
    assert req["still_source"].get("ok") is True
    assert req["still_source"].get("sha256") == first.get("sha256")


def test_inventory_summary_line_nonempty() -> None:
    line = inventory_summary_line()
    assert "still=" in line
    assert "motion=" in line
    assert "audio=" in line


def test_comfy_blocked_no_stale_meat_denial() -> None:
    armory_path = Path(__file__).resolve().parents[1] / "registry" / "comfy-weapons.json"
    data = json.loads(armory_path.read_text(encoding="utf-8"))
    blocked = {b.get("intent") for b in (data.get("blocked_capabilities") or [])}
    assert "adult-meat-motion-production" not in blocked
    selected = select_weapon("adult-meat-motion-i2v", stage="production")
    assert selected["weapon"]["id"] == "minimax-h3-i2v-pilot"


def test_inventory_report_and_router_line(tmp_path: Path) -> None:
    from weapon_inventory import inventory_report

    rep = inventory_report(validate=True, primary_for_demand="text-to-image")
    assert rep["ok"] is True
    assert rep["primary_for"]["id"] == "qwen-image-2512-quality"
    assert "still=" in rep["line"]
    route = build_weapon_route(
        tmp_path,
        workflow={"mode": "professional", "current_stage": "shot_animatic_lock"},
    )
    assert route["inventory_line"]
    assert "motion=" in route["inventory_line"]


def test_compact_exposes_weapon_inventory_line() -> None:
    from dispatch_compact import compact_dispatch

    packet = {
        "ok": True,
        "kind": "ai-film-dispatch",
        "schema_version": 2,
        "craft_stage": "media",
        "pipeline_stage": "visual",
        "next_id": "x",
        "next_cmd": "echo",
        "next_why": "test",
        "next_action": {"id": "x", "cmd": "echo", "skill_id": ""},
        "weapon_route": {
            "status": "ready",
            "weapon_id": "qwen-image-2512-quality",
            "inventory_line": "still=qwen · motion=h3 · audio=edge",
        },
        "metrics": {},
        "workflow": {},
        "state_hash": "abc",
    }
    c = compact_dispatch(packet)
    assert c.get("weapon_inventory_line") == "still=qwen · motion=h3 · audio=edge"

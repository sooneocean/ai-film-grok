"""H3 FLF media pack + multi-ref + promote-as-end (no GPU)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from comfy_armory import (  # noqa: E402
    assert_registered_weapon_workflow,
    compile_weapon_workflow,
)
from h3_media_pack import (  # noqa: E402
    r2v_ref_prompt_clause,
    resolve_identity_refs,
    resolve_last_frame_path,
    resolve_media_pack,
)
from h3_mode import resolve_h3_mode  # noqa: E402
from h3_workflow import plan_h3_shot  # noqa: E402
from still_challenge import promote_still_challenge  # noqa: E402


def _png(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)
    return path


def _film(tmp_path: Path, *, with_end: bool = False, with_cast: bool = False) -> Path:
    root = tmp_path / "film"
    root.mkdir()
    still = _png(root / "stills" / "s_meat.png")
    if with_end:
        _png(root / "stills" / "s_meat_end.png")
    if with_cast:
        cast = _png(root / "cast" / "hero.png")
        bible = {
            "schema_version": 2,
            "characters": {"hero": {"reference_image": {"path": str(cast.relative_to(root))}}},
            "cast_masters": {},
            "cast_state_masters": {},
        }
        (root / "style-bible.json").write_text(json.dumps(bible), encoding="utf-8")
    spec = {
        "title": "h3-flf",
        "aspect_ratio": "9:16",
        "_i2v_profile": "hybrid_h3",
        "h3": {"enabled": True, "audio_policy": "prefer_native"},
        "scenes": [
            {
                "id": "sc1",
                "shots": [
                    {
                        "id": "s_meat",
                        "shot_role": "hero",
                        "heat_phase": "act",
                        "wardrobe_state": "bare",
                        "dramatic_function": "action",
                        "cast_id": "hero" if with_cast else None,
                        "nar": "body motion toward end pose",
                    }
                ],
            }
        ],
    }
    (root / "film-spec.json").write_text(json.dumps(spec), encoding="utf-8")
    (root / "manifest.json").write_text(
        json.dumps({"stills": {"s_meat": {"path": str(still), "status": "approved"}}}),
        encoding="utf-8",
    )
    return root


def test_resolve_last_frame_convention(tmp_path: Path) -> None:
    root = _film(tmp_path, with_end=True)
    path, source = resolve_last_frame_path(root, "s_meat")
    assert path is not None
    assert path.name == "s_meat_end.png"
    assert source == "stills_end"


def test_media_pack_has_first_and_last(tmp_path: Path) -> None:
    root = _film(tmp_path, with_end=True)
    pack = resolve_media_pack(root, "s_meat", approved_still=root / "stills" / "s_meat.png")
    assert pack["has_first"] is True
    assert pack["has_last"] is True


def test_media_pack_rejects_identical_first_last(tmp_path: Path) -> None:
    root = _film(tmp_path, with_end=False)
    still = root / "stills" / "s_meat.png"
    pack = resolve_media_pack(root, "s_meat", approved_still=still, last_override=still)
    assert pack["has_last"] is False


def test_media_pack_missing_last_hint(tmp_path: Path) -> None:
    root = _film(tmp_path, with_end=False)
    pack = resolve_media_pack(root, "s_meat", approved_still=root / "stills" / "s_meat.png")
    assert pack["missing_last_hint"]
    assert "stills/s_meat_end.png" in pack["missing_last_hint"]["suggested_paths"][0]


def test_identity_refs_from_bible_cast(tmp_path: Path) -> None:
    root = _film(tmp_path, with_cast=True)
    shot = {"id": "s_meat", "cast_id": "hero"}
    refs = resolve_identity_refs(root, shot)
    assert refs
    assert any("hero.png" in r["path"] for r in refs)


def test_plan_includes_cast_refs(tmp_path: Path) -> None:
    root = _film(tmp_path, with_end=True, with_cast=True)
    plan = plan_h3_shot(root, "s_meat")
    assert plan["mode"] == "flf"
    assert plan.get("ref_paths") or plan["media_pack"].get("refs") is not None


def test_mode_flf_when_last_present() -> None:
    shot = {
        "id": "s1",
        "shot_role": "hero",
        "heat_phase": "act",
        "wardrobe_state": "bare",
        "dramatic_function": "action",
    }
    r = resolve_h3_mode(shot, has_still=True, has_last=True)
    assert r["mode"] == "flf"
    assert "first_last_primary" in r["reasons"]


def test_force_r2v_keeps_r2v_even_with_last() -> None:
    shot = {
        "id": "s1",
        "shot_role": "hero",
        "heat_phase": "act",
        "wardrobe_state": "bare",
        "force_r2v": True,
    }
    r = resolve_h3_mode(shot, has_still=True, has_last=True)
    assert r["mode"] == "r2v"
    assert r.get("uses_last_as_pose_ref") is True


def test_mode_continue_with_last_is_flf() -> None:
    shot = {
        "id": "s2",
        "shot_role": "hero",
        "heat_phase": "act",
        "wardrobe_state": "bare",
        "dsl": {"chain_mode": "continue"},
        "force_r2v": True,
    }
    r = resolve_h3_mode(shot, has_still=True, has_last=True, wants_continue=True)
    assert r["mode"] == "flf"


def test_mode_continue_without_last_stays_i2v() -> None:
    shot = {
        "id": "s2",
        "shot_role": "hero",
        "heat_phase": "act",
        "wardrobe_state": "bare",
        "dsl": {"chain_mode": "continue"},
    }
    r = resolve_h3_mode(shot, has_still=True, has_last=False, wants_continue=True)
    assert r["mode"] == "i2v"


def test_plan_selects_flf_with_end_still(tmp_path: Path) -> None:
    root = _film(tmp_path, with_end=True)
    plan = plan_h3_shot(root, "s_meat")
    assert plan["mode"] == "flf"
    assert plan["last_path"]


def test_plan_without_end_stays_i2v(tmp_path: Path) -> None:
    root = _film(tmp_path, with_end=False)
    plan = plan_h3_shot(root, "s_meat")
    assert plan["mode"] == "i2v"
    assert plan.get("missing_last_hint")


def test_compile_i2v_without_last_unchanged() -> None:
    graph = compile_weapon_workflow(
        "minimax-h3-i2v-pilot",
        prompt="Vertical 9:16 motion plate with body action.",
        seed=1,
        input_image_name="aifilm/first.png",
    )
    assert "20" not in graph
    assert "last_frame" not in graph["8"]["inputs"]
    assert_registered_weapon_workflow("http://127.0.0.1:18188", "minimax-h3-i2v-pilot", graph)


def test_compile_i2v_with_last_injects_loadimage() -> None:
    graph = compile_weapon_workflow(
        "minimax-h3-i2v-pilot",
        prompt="Vertical 9:16 first-last-frame motion toward end pose.",
        seed=2,
        input_image_name="aifilm/first.png",
        last_image_name="aifilm/last.png",
    )
    assert graph["20"]["class_type"] == "LoadImage"
    assert graph["8"]["inputs"]["last_frame"] == ["20", 0]
    assert_registered_weapon_workflow("http://127.0.0.1:18188", "minimax-h3-i2v-pilot", graph)


def test_compile_r2v_multi_ref_injects_slots() -> None:
    graph = compile_weapon_workflow(
        "minimax-h3-r2v-pilot",
        prompt="Vertical 9:16. Use <Picture 1> identity. High motion body action.",
        seed=3,
        input_image_name="aifilm/first.png",
        ref_image_names=["aifilm/id.png", "aifilm/pose.png"],
    )
    assert graph["21"]["inputs"]["image"] == "aifilm/id.png"
    assert graph["22"]["inputs"]["image"] == "aifilm/pose.png"
    assert graph["8"]["inputs"]["ref_images.ref_image_1"] == ["21", 0]
    assert graph["8"]["inputs"]["ref_images.ref_image_2"] == ["22", 0]
    assert_registered_weapon_workflow("http://127.0.0.1:18188", "minimax-h3-r2v-pilot", graph)


def test_r2v_ref_prompt_clause() -> None:
    clause = r2v_ref_prompt_clause([{"role": "identity"}, {"role": "pose"}])
    assert "<Picture 1>" in clause
    assert "<Picture 2>" in clause
    assert "identity" in clause.lower()


def test_promote_as_end(tmp_path: Path) -> None:
    root = _film(tmp_path, with_end=False)
    cand = _png(root / "takes" / "s_meat" / "still_frw_endpose.png")
    report = promote_still_challenge(
        root,
        "s_meat",
        source=cand,
        identity_approved=True,
        anatomy_safe=True,
        review_note="end pose for FLF",
        as_role="end",
        status="candidate",  # fake PNG skips approved geometry gate
    )
    assert report["ok"] is True
    assert report["role"] == "end"
    end = root / "stills" / "s_meat_end.png"
    assert end.is_file()
    path, source = resolve_last_frame_path(root, "s_meat")
    assert path == end.resolve()
    plan = plan_h3_shot(root, "s_meat")
    assert plan["mode"] == "flf"


def test_explicit_flf_without_last_falls_back_i2v() -> None:
    shot = {"id": "s1", "h3_mode": "flf", "shot_role": "hero", "heat_phase": "act"}
    r = resolve_h3_mode(shot, has_still=True, has_last=False)
    assert r["mode"] == "i2v"

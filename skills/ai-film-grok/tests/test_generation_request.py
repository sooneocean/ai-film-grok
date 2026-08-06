"""GenerationRequest facade + receipt + pixel hash gate."""

from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from generation_request import (  # noqa: E402
    assert_pixel_pack_current,
    build_generation_request,
    load_generation_request,
    request_receipt_path,
    validate_pixel_pack_hashes,
)
from h3_workflow import plan_h3_shot  # noqa: E402


def _png(path: Path, tag: bytes = b"A") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + tag * 32)
    return path


def _film(tmp_path: Path, *, with_end: bool = False) -> Path:
    root = tmp_path / "film"
    root.mkdir()
    still = _png(root / "stills" / "s01.png", b"1")
    if with_end:
        _png(root / "stills" / "s01_end.png", b"2")
    spec = {
        "title": "gen-req",
        "aspect_ratio": "9:16",
        "director_intent": {
            "logline": "test",
            "theme": "test",
            "protagonist_want": "escape",
        },
        "h3": {"enabled": True},
        "scenes": [
            {
                "id": "sc1",
                "shots": [
                    {
                        "id": "s01",
                        "shot_role": "hero",
                        "heat_phase": "setup",
                        "wardrobe_state": "full",
                        "dramatic_function": "hook",
                        "visible_change": "she steps into the doorway",
                        "dsl": {
                            "action": "steps into doorway",
                            "motion": "walk forward two steps",
                            "camera": {"shot_size": "ms"},
                        },
                        "duration_sec": 4,
                        "nar": "她走进门。",
                    }
                ],
            }
        ],
    }
    (root / "film-spec.json").write_text(json.dumps(spec), encoding="utf-8")
    (root / "manifest.json").write_text(
        json.dumps({"stills": {"s01": {"path": str(still), "status": "approved"}}}),
        encoding="utf-8",
    )
    (root / "style-bible.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "signature_block": "cel anime clean line vertical drama medium lock cel",
                "medium": "anime",
                "style_fingerprint": {"medium_key": "anime", "medium": "cel anime"},
                "cast_masters": {},
                "cast_locks": {},
            }
        ),
        encoding="utf-8",
    )
    return root


def test_build_i2v_request_writes_refs(tmp_path: Path) -> None:
    root = _film(tmp_path)
    req = build_generation_request(root, "s01", kind="i2v", write=True)
    assert req["kind"] == "generation-request"
    assert req["generation_kind"] == "i2v"
    assert req["image_refs"]
    assert req["image_refs"][0]["role"] in {"first", "state_photo"}
    assert req["image_refs"][0]["sha256"]
    assert req["text_sha256"]
    assert request_receipt_path(root, "s01").is_file()
    loaded = load_generation_request(root, "s01")
    assert loaded and loaded["text_sha256"] == req["text_sha256"]


def test_build_still_kind(tmp_path: Path) -> None:
    root = _film(tmp_path)
    req = build_generation_request(root, "s01", kind="still", write=False)
    assert req["generation_kind"] == "still"
    assert "text_prompt" in req


def test_location_asset_hint(tmp_path: Path) -> None:
    root = _film(tmp_path)
    (root / "assets-registry.json").write_text(
        json.dumps(
            {
                "locations": {
                    "cave": {
                        "description": "damp stone cave",
                        "lighting": "warm torch",
                        "palette": "ochre",
                        "immutableRules": ["no daylight"],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    # patch shot location into film-spec
    spec = json.loads((root / "film-spec.json").read_text(encoding="utf-8"))
    spec["scenes"][0]["shots"][0]["locationId"] = "cave"
    (root / "film-spec.json").write_text(json.dumps(spec), encoding="utf-8")
    req = build_generation_request(root, "s01", kind="i2v", write=False)
    assert "Location lock" in req["text_prompt"] or "damp stone" in req["text_prompt"]


def test_pixel_pack_hash_mismatch(tmp_path: Path) -> None:
    root = _film(tmp_path)
    req = build_generation_request(root, "s01", kind="i2v", write=True)
    assert req["ok"] is True
    bad = _png(root / "stills" / "other.png", b"Z")
    report = validate_pixel_pack_hashes(root, shot_id="s01", inputs=[bad])
    assert report["ok"] is False


def test_pixel_pack_match_ok(tmp_path: Path) -> None:
    root = _film(tmp_path)
    still = root / "stills" / "s01.png"
    build_generation_request(root, "s01", kind="i2v", write=True)
    assert_pixel_pack_current(root, "s01", inputs=[still])  # no raise


def test_h3_plan_writes_generation_request(tmp_path: Path) -> None:
    root = _film(tmp_path, with_end=True)
    plan = plan_h3_shot(root, "s01")
    assert plan.get("generation_request")
    assert plan["generation_request"].get("receipt")
    assert request_receipt_path(root, "s01").is_file()

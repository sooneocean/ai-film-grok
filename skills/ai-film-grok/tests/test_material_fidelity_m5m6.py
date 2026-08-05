from __future__ import annotations
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from dispatch_compact import compact_dispatch
from generation_ready import generation_ready_report
from h3_media_pack import resolve_media_pack
from identity_refs import resolve_identity_refs, resolve_identity_refs_report

def _png(path, tag=b"A"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + tag * 20)
    return path

def test_canonical_cast_preferred_over_legacy(tmp_path):
    root = tmp_path / "film"; root.mkdir()
    _png(root / "cast" / "hero.png", b"L")
    canon = _png(root / "canonical" / "cast" / "hero.png", b"C")
    (root / "style-bible.json").write_text("{}", encoding="utf-8")
    refs = resolve_identity_refs(root, {"id": "s1", "cast_id": "hero"}, max_refs=3)
    assert refs and refs[0]["path"] == str(canon.resolve())

def test_legacy_only_soft_warn(tmp_path):
    root = tmp_path / "film"; root.mkdir()
    _png(root / "cast" / "hero.png", b"L")
    rep = resolve_identity_refs_report(root, {"id": "s1", "cast_id": "hero"})
    assert rep["legacy_count"] >= 1 and any("LEGACY_CAST_PATH" in w for w in rep["warnings"])

def test_media_pack_flf_ready_and_mode_hint(tmp_path):
    root = tmp_path / "film"; root.mkdir()
    still = _png(root / "stills" / "s1.png"); _png(root / "stills" / "s1_end.png")
    pack = resolve_media_pack(root, "s1", approved_still=still)
    assert pack.get("flf_ready") is True and pack.get("mode_hint") == "flf"

def test_media_pack_missing_last_mode_hint_i2v(tmp_path):
    root = tmp_path / "film"; root.mkdir()
    still = _png(root / "stills" / "s1.png")
    pack = resolve_media_pack(root, "s1", approved_still=still)
    assert pack.get("flf_ready") is False and pack["missing_last_hint"]["mode_with_last"] == "flf"

def test_generation_ready_report(tmp_path):
    root = tmp_path / "film"; root.mkdir(); _png(root / "stills" / "s01.png")
    (root / "film-spec.json").write_text(json.dumps({"title":"m6","scenes":[{"id":"sc1","shots":[{"id":"s01","wardrobe_state":"full"}]}]}), encoding="utf-8")
    (root / "style-bible.json").write_text(json.dumps({"locked": True, "state": "Approved", "style_fingerprint": {"medium_key": "anime"}}), encoding="utf-8")
    rep = generation_ready_report(root)
    assert rep["kind"] == "generation-ready" and rep["style_locked"] is True

def test_compact_dispatch_exposes_generation_ready():
    packet = {"ok": True, "kind": "ai-film-dispatch", "schema_version": 2, "craft_stage": "media", "pipeline_stage": "visual", "next_id": "x", "next_cmd": "echo", "next_why": "test", "next_action": {"id": "x", "cmd": "echo", "skill_id": ""}, "weapon_route": {"status": "ready"}, "generation_ready": {"ok": True, "line": "style=lock · flf=1/2", "style_locked": True, "still_source_ok": True, "flf_eligible": 1, "flf_missing_last": 1, "peak_missing": [], "blockers": []}, "metrics": {}, "workflow": {}, "state_hash": "abc"}
    c = compact_dispatch(packet)
    assert c.get("generation_ready") and c["generation_ready"]["style_locked"] is True

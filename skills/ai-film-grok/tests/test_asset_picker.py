"""Tests for asset selection + shot -> manifest.json binding (P5).

P5 core rule: a *shot* approval is the only kind that belongs in the production
``manifest.json`` (``clips[shot_id]`` with status ``approved``).  character /
voice / bgm are owned by other canonical files and MUST NOT be invented into
manifest.json.  We assert both the happy path and the "never invents state"
contract.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from asset_picker import list_assets, select_asset
from web_core import WebConsoleConflict, WebConsoleForbidden

pytestmark = pytest.mark.console


def _seed(root: Path) -> None:
    (root / "receipts").mkdir(parents=True, exist_ok=True)
    # non-blocking spec: adult genre but heat_scale=max (adult_scale IRON pass),
    # zh voice (voice_lang pass).  Heavy gates degrade to "unknown" (not blocking).
    (root / "film-spec.json").write_text(
        json.dumps({"genre": "adult", "heat_scale": "max", "cast_voices": {"f": "zh-CN-XiaoyiNeural"}}),
        encoding="utf-8",
    )


def test_shot_select_binds_existing_manifest(tmp_path):
    _seed(tmp_path)
    # pre-existing production manifest with a still-in-progress clip record
    manifest = {
        "schema_version": 2,
        "clips": {
            "s1": {
                "shot_id": "s1",
                "status": "completed",
                "path": "clips/s1.mp4",
                "sha256": "abc",
                "provider": "grok-imagine",
            }
        },
        "stills": {},
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    res = select_asset(tmp_path, kind="shot", asset_id="s1", expected_revision=None)
    assert res["ok"] is True
    b = res["manifest_binding"]
    assert b["bound"] is True
    assert b["shot_id"] == "s1"
    assert b["status"] == "approved"
    assert b.get("bootstrapped") is not True

    saved = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    rec = saved["clips"]["s1"]
    assert rec["status"] == "approved"          # promoted
    assert rec["path"] == "clips/s1.mp4"        # existing fields preserved
    assert rec["provider"] == "grok-imagine"


def test_shot_select_bootstraps_missing_manifest(tmp_path):
    _seed(tmp_path)
    assert not (tmp_path / "manifest.json").exists()

    res = select_asset(tmp_path, kind="shot", asset_id="s2", expected_revision=None)
    b = res["manifest_binding"]
    assert b["bound"] is True
    assert b["shot_id"] == "s2"
    assert b["status"] == "approved"
    assert b.get("bootstrapped") is True         # a minimal manifest was created

    saved = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert saved["clips"]["s2"]["status"] == "approved"
    assert saved["schema_version"] == 2          # canonical shape, not invented


def test_non_shot_kind_does_not_bind_manifest(tmp_path):
    _seed(tmp_path)
    res = select_asset(tmp_path, kind="voice", asset_id="f", expected_revision=None)
    # voice selection must NOT create / touch a production manifest
    assert res.get("manifest_binding") is None
    assert not (tmp_path / "manifest.json").exists()
    # ledger + receipt still written (audit trail preserved)
    ledger = json.loads((tmp_path / "receipts" / "selection-ledger.json").read_text(encoding="utf-8"))
    assert ledger["selections"][0]["kind"] == "voice"


def test_select_revision_conflict_raises_and_does_not_bind(tmp_path):
    _seed(tmp_path)
    (tmp_path / "manifest.json").write_text(json.dumps({"schema_version": 2, "clips": {}, "stills": {}}), encoding="utf-8")
    select_asset(tmp_path, kind="shot", asset_id="s1", expected_revision=None)
    saved_before = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    # stale revision -> must reject and leave the manifest exactly as-is
    with pytest.raises(WebConsoleConflict):
        select_asset(tmp_path, kind="shot", asset_id="s1", expected_revision=0)
    saved_after = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert saved_after == saved_before           # conflict left manifest untouched


def test_shot_select_without_review_queue_is_soft_and_still_binds(tmp_path):
    """When the cloud review queue is unavailable, binding still succeeds
    (best-effort enrichment is optional; status approved is the contract)."""
    _seed(tmp_path)
    res = select_asset(tmp_path, kind="shot", asset_id="s9", expected_revision=None)
    assert res["manifest_binding"]["bound"] is True
    saved = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert saved["clips"]["s9"]["status"] == "approved"
    assert saved["clips"]["s9"]["provider"] == "console"   # fallback, no invented state


def test_select_blocked_when_gate_fails(tmp_path):
    """P6: a failed hard gate must reject selection server-side (403) and must
    NOT write the ledger or bind the manifest (fail-closed)."""
    (tmp_path / "film-spec.json").write_text(
        json.dumps({"genre": "adult", "heat_scale": "normal"}),  # adult_scale IRON fail
        encoding="utf-8",
    )
    with pytest.raises(WebConsoleForbidden):
        select_asset(tmp_path, kind="shot", asset_id="s1", expected_revision=None)
    assert not (tmp_path / "receipts" / "selection-ledger.json").exists()
    assert not (tmp_path / "manifest.json").exists()


def test_select_allowed_when_no_hard_fail(tmp_path):
    """P6: gates that degrade to 'unknown'/'skipped'/'warn' must NOT block
    (fail-open) — an unwired heavy gate must never lock the console."""
    (tmp_path / "receipts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "film-spec.json").write_text(
        json.dumps({"genre": "documentary", "cast_voices": {"f": "zh-CN-XiaoyiNeural"}}),
        encoding="utf-8",
    )
    res = select_asset(tmp_path, kind="voice", asset_id="f", expected_revision=None)
    assert res["ok"] is True


# --------------------------------------------------------------------------- #
# P7 — production integration: console selection drives canonical pipeline files
# --------------------------------------------------------------------------- #
def test_voice_select_pins_cast_voice_in_spec(tmp_path):
    (tmp_path / "receipts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "film-spec.json").write_text(
        json.dumps({"genre": "documentary", "cast_voices": {}}), encoding="utf-8"
    )
    res = select_asset(
        tmp_path, kind="voice", asset_id="female_lead",
        value="zh-CN-XiaoyiNeural", expected_revision=None,
    )
    assert res["ok"] is True
    cb = res["canonical_binding"]
    assert cb["bound"] is True
    assert cb["field"] == "cast_voices"
    assert cb["value"] == "zh-CN-XiaoyiNeural"
    spec = json.loads((tmp_path / "film-spec.json").read_text(encoding="utf-8"))
    assert spec["cast_voices"]["female_lead"] == "zh-CN-XiaoyiNeural"


def test_voice_select_without_value_pins_current_voice(tmp_path):
    (tmp_path / "receipts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "film-spec.json").write_text(
        json.dumps({"genre": "documentary", "cast_voices": {"lead": "zh-CN-YunxiNeural"}}),
        encoding="utf-8",
    )
    res = select_asset(tmp_path, kind="voice", asset_id="lead", expected_revision=None)
    cb = res["canonical_binding"]
    assert cb["bound"] is True
    spec = json.loads((tmp_path / "film-spec.json").read_text(encoding="utf-8"))
    assert spec["cast_voices"]["lead"] == "zh-CN-YunxiNeural"


def test_character_select_marks_selected_in_assets(tmp_path):
    (tmp_path / "receipts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "assets.json").write_text(
        json.dumps({"characters": [{"id": "hero", "name": "阿强", "role": "lead"}]}),
        encoding="utf-8",
    )
    res = select_asset(tmp_path, kind="character", asset_id="hero", expected_revision=None)
    assert res["ok"] is True
    cb = res["canonical_binding"]
    assert cb["bound"] is True
    assert cb["field"] == "characters[].selected"
    reg = json.loads((tmp_path / "assets.json").read_text(encoding="utf-8"))
    hero = next(c for c in reg["characters"] if str(c["id"]) == "hero")
    assert hero.get("selected") is True


def test_shot_select_uses_real_candidate_fields(tmp_path, monkeypatch):
    """P7: when the cloud review queue carries real candidate metadata, the
    manifest binding must carry the true path / sha256 / provider (not the
    'console' fallback)."""
    (tmp_path / "receipts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "film-spec.json").write_text(
        json.dumps({"genre": "documentary"}), encoding="utf-8"
    )

    def fake_queue(base):
        return {
            "items": [
                {
                    "id": "shot:s1",
                    "cloud_candidates": [
                        {
                            "id": "c1",
                            "provider": "grok-imagine",
                            "model": "grok-imagine-video-1.5",
                            "status": "approved",
                            "path": "clips/s1.mp4",
                            "sha256": "deadbeef",
                        }
                    ],
                }
            ]
        }

    monkeypatch.setattr("review_control.review_queue", fake_queue)
    res = select_asset(tmp_path, kind="shot", asset_id="s1", expected_revision=None)
    b = res["manifest_binding"]
    assert b["bound"] is True
    assert b["provider"] == "grok-imagine"
    assert b["path"] == "clips/s1.mp4"
    saved = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    rec = saved["clips"]["s1"]
    assert rec["sha256"] == "deadbeef"
    assert rec["provider"] == "grok-imagine"


def test_scene_and_prop_listing_is_readonly(tmp_path):
    """P7: scene/prop panels surface existing pipeline data read-only (no
    invented state, no write to canonical files)."""
    (tmp_path / "film-spec.json").write_text(
        json.dumps(
            {
                "genre": "documentary",
                "scenes": [
                    {"id": "sc01", "title": "开场", "shots": [{"id": "s1"}]},
                    {"id": "sc02", "title": "高潮", "shots": []},
                ],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "assets.json").write_text(
        json.dumps({"bible": {"props": {"ring": {"description": "订婚戒指"}}}}),
        encoding="utf-8",
    )
    scenes = list_assets(tmp_path, kind="scene")
    assert scenes["kind"] == "scene"
    assert [s["scene_id"] for s in scenes["items"]] == ["sc01", "sc02"]
    assert scenes["items"][0]["shot_count"] == 1

    props = list_assets(tmp_path, kind="prop")
    assert props["kind"] == "prop"
    assert props["items"][0]["description"] == "订婚戒指"

    # selecting a scene must NOT mutate canonical files (read-only intent)
    (tmp_path / "receipts").mkdir(parents=True, exist_ok=True)
    res = select_asset(tmp_path, kind="scene", asset_id="sc01", expected_revision=None)
    assert res["canonical_binding"]["bound"] is False
    assert res["manifest_binding"] is None



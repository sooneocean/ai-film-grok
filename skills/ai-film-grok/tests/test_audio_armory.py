from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from audio_armory import inspect_audio_armory, plan_audio_weapon  # noqa: E402


def test_armory_only_promotes_receipt_backed_audio_weapons(tmp_path: Path) -> None:
    wav = tmp_path / "candidate.wav"
    wav.write_bytes(b"not-a-real-wav")
    # Avoid a media fixture here: seed a minimal catalog through the public
    # shape, keeping this test about route evidence rather than DSP decoding.
    (tmp_path / "catalog.json").write_text(
        '{"schema":"aifilm-bgm-library-v1","revision":1,"assets":{"x":{"status":"pending_human_review","technical":{"ok":true,"duration_sec":20},"parent_asset_id":"master","edit_variant":"dialogue-safe","transition_to_asset_id":"to"}}}',
        encoding="utf-8",
    )
    node = {"ok": True, "models": {"music": True}}
    report = inspect_audio_armory(tmp_path, node=node)
    states = {item["intent"]: item["state"] for item in report["weapons"]}
    assert states["scene_edit"] == "verified"
    assert states["transition_bridge"] == "verified"
    assert states["motif_development"] == "conditional"
    assert any(item["intent"] == "seamless_loop" for item in report["excluded"])


def _approved_catalog(tmp_path: Path) -> None:
    (tmp_path / "catalog.json").write_text(
        '{"schema":"aifilm-bgm-library-v1","revision":1,"assets":{"master":{"status":"approved","technical":{"ok":true,"duration_sec":30}},"to":{"status":"approved","technical":{"ok":true,"duration_sec":30}},"edit":{"status":"pending_human_review","technical":{"ok":true,"duration_sec":20},"parent_asset_id":"master","edit_variant":"dialogue-safe","transition_to_asset_id":"to"}}}',
        encoding="utf-8",
    )


def test_armory_plans_without_running_generation_or_approval(tmp_path: Path) -> None:
    _approved_catalog(tmp_path)
    report = plan_audio_weapon(
        tmp_path,
        node={"ok": True, "models": {"music": True}, "music_reference_upload": True},
        intent="scene_edit",
        asset_id="master",
        duration_sec=18,
    )
    assert report["state"] == "ready_to_stage"
    assert report["auto_execute"] is False
    assert report["writes_catalog"] is False
    assert report["approval_required"] is True
    assert report["candidate_command_templates"][0][-2:] == ["--variant", "dialogue-safe"]


def test_motif_plan_requires_human_approved_series_master(tmp_path: Path) -> None:
    _approved_catalog(tmp_path)
    report = plan_audio_weapon(
        tmp_path,
        node={"ok": True, "models": {"music": True}, "music_reference_upload": True},
        intent="motif_development",
        film_root="artifacts/demo",
        series_id="demo-series",
    )
    assert report["state"] == "blocked"
    assert "approved_series_motif_asset_id" in report["missing_prerequisites"]
    assert report["candidate_command_templates"][0][2] == "series-pack"
    assert "two-stage" in report["note"]


def test_motif_plan_requires_a_same_series_series_pack_asset(tmp_path: Path) -> None:
    _approved_catalog(tmp_path)
    catalog_path = tmp_path / "catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    catalog["assets"]["series-master"] = {
        "status": "approved",
        "technical": {"ok": True, "duration_sec": 60},
        "series_id": "demo-series",
        "motif_family": "protagonist",
        "parent_asset_id": "master",
        "recipe": {"recipe_id": "series-demo-series-protagonist-low"},
    }
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
    node = {"ok": True, "models": {"music": True}, "music_reference_upload": True}
    unrelated = plan_audio_weapon(
        tmp_path,
        node=node,
        intent="motif_development",
        asset_id="master",
        film_root="artifacts/demo",
        series_id="demo-series",
    )
    assert unrelated["state"] == "blocked"
    staged = plan_audio_weapon(
        tmp_path,
        node=node,
        intent="motif_development",
        asset_id="series-master",
        film_root="artifacts/demo",
        series_id="demo-series",
    )
    assert staged["state"] == "canary_required"
    assert staged["real_node_canary_required"] is True
    assert staged["candidate_command_templates"][0][2] == "motif-development"


def test_armory_rejects_unknown_intent(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unsupported ACE audio intent"):
        plan_audio_weapon(tmp_path, node=None, intent="seamless_loop")


@pytest.mark.parametrize("duration", (0, -1, float("nan"), float("inf")))
def test_armory_rejects_invalid_duration(tmp_path: Path, duration: float) -> None:
    with pytest.raises(ValueError, match="duration"):
        plan_audio_weapon(tmp_path, node=None, intent="score_master", duration_sec=duration)

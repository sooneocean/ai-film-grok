from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from i2v_provider import preferred  # noqa: E402
from production_gates import ProductionGateError, assert_provider_pilot_current  # noqa: E402
from quality_gates import (  # noqa: E402
    evaluate_clip,
    evaluate_keyframe,
    shot_role,
    summarize_quality,
)


def _root(tmp_path: Path, *, shot_role_value: str | None = None) -> Path:
    root = tmp_path / "film"
    root.mkdir(parents=True)
    shot = {"id": "shot01", "dramatic_function": "action"}
    if shot_role_value:
        shot["shot_role"] = shot_role_value
    (root / "film-spec.json").write_text(
        json.dumps({"scenes": [{"shots": [shot]}]}, ensure_ascii=False), encoding="utf-8"
    )
    return root


def test_hero_is_default_and_environment_is_explicit(tmp_path: Path) -> None:
    hero = _root(tmp_path)
    assert shot_role(hero, "shot01") == "hero"
    env = _root(tmp_path / "env", shot_role_value="env")
    assert shot_role(env, "shot01") == "environment"


def test_keyframe_rejects_missing_source_and_prompt_artifact(tmp_path: Path) -> None:
    root = _root(tmp_path)
    prompt = root / "prompt.txt"
    prompt.write_text("portrait, shot01, keep the face", encoding="utf-8")
    report = evaluate_keyframe(
        root,
        shot_id="shot01",
        source=root / "missing.png",
        aspect_ratio="9:16",
        prompt_file=prompt,
        identity_approved=True,
        review_note="identity checked",
    )
    assert report["ok"] is False
    assert "KEYFRAME_MISSING" in report["codes"]
    assert "KEYFRAME_PROMPT_ARTIFACT_TEXT" in report["codes"]


def test_hero_clip_requires_approved_review_and_all_scores(tmp_path: Path) -> None:
    root = _root(tmp_path)
    qa = {"ok": True, "decode_ok": True, "motion_ok": True}
    report = evaluate_clip(
        root,
        shot_id="shot01",
        qa=qa,
        endpoint="image_to_video",
        identity_approved=True,
        motion_approved=True,
        review={
            "approved": True,
            "scorecard": {"dimensions": {"identity": 4, "continuity": 4}},
        },
    )
    assert report["ok"] is False
    assert "HERO_SHOT_REVIEW_SCORE_LOW" in report["codes"]


def test_environment_clip_keeps_technical_gate_without_hero_review(tmp_path: Path) -> None:
    root = _root(tmp_path, shot_role_value="env")
    report = evaluate_clip(
        root,
        shot_id="shot01",
        qa={"ok": True, "decode_ok": True, "motion_ok": True},
        endpoint="frw_ltx_t2v",
        identity_approved=False,
        motion_approved=False,
        review=None,
    )
    assert report["ok"] is True
    assert report["role"] == "environment"


def test_provider_selection_writes_evidence_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIFILM_I2V_PROFILE", "grok_primary")
    provider = preferred(root=tmp_path)
    assert provider.name == "grok"
    receipt = json.loads((tmp_path / "receipts" / "i2v-routing.json").read_text())
    assert receipt["selected_provider"] == "grok"
    assert receipt["fallback"] is False
    assert receipt["requires_hero_repilot"] is False


def test_provider_fallback_requires_new_pilot_evidence(tmp_path: Path) -> None:
    receipts = tmp_path / "receipts"
    receipts.mkdir()
    (receipts / "i2v-routing.json").write_text(
        json.dumps({"selected_provider": "grok", "requires_hero_repilot": True}),
        encoding="utf-8",
    )
    (receipts / "pilot-approval.json").write_text(
        json.dumps({"approved": True, "approved_by": "user"}), encoding="utf-8"
    )
    with pytest.raises(ProductionGateError, match="new user-approved pilot"):
        assert_provider_pilot_current(tmp_path)


def test_quality_summary_reports_failures_and_supports_shot_filter(tmp_path: Path) -> None:
    root = _root(tmp_path)
    quality_dir = root / "receipts" / "quality"
    quality_dir.mkdir(parents=True)
    (quality_dir / "shot01.json").write_text(
        json.dumps(
            {
                "shot_id": "shot01",
                "kind": "clip-quality",
                "ok": False,
                "codes": ["HERO_MOTION_REVIEW_MISSING"],
                "hard": ["hero clip requires full-clip motion approval"],
            }
        ),
        encoding="utf-8",
    )
    (quality_dir / "shot02.json").write_text(
        json.dumps({"shot_id": "shot02", "kind": "keyframe-quality", "ok": True}),
        encoding="utf-8",
    )

    report = summarize_quality(root)
    assert report["status"] == "blocked"
    assert report["ok"] is False
    assert report["receipt_count"] == 2
    assert report["failed_shots"][0]["shot_id"] == "shot01"

    filtered = summarize_quality(root, shot_id="shot02")
    assert filtered["status"] == "pass"
    assert filtered["ok"] is True
    assert filtered["receipt_count"] == 1


def test_quality_summary_empty_root_is_actionable_but_not_blocked(tmp_path: Path) -> None:
    report = summarize_quality(_root(tmp_path))
    assert report["status"] == "no_receipts"
    assert report["ok"] is True
    assert report["receipt_count"] == 0

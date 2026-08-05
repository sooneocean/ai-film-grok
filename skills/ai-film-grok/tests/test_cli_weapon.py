from __future__ import annotations

import json
import sys
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from cli_weapon import WeaponControlError, promotion_packet, run_weapon  # noqa: E402


def _completed_canary(*, weapon_id: str = "ltx2-broll-pilot", sha: str = "abc123") -> dict:
    return {
        "weapon_id": weapon_id,
        "status": "completed",
        "artifact": {
            "output_sha256": sha,
            "technical_qa": {"ok": True, "decode_ok": True},
        },
    }


def test_canary_is_a_plan_without_execute_or_remote_submission(capsys) -> None:
    args = Namespace(
        weapon_action="canary",
        weapon_id="qwen-image-edit-2511-local",
        base_url="http://127.0.0.1:18188",
        execute=False,
        complete=False,
        confirm=False,
        workflow=None,
        timeout=60,
        receipt=None,
        submission_receipt=None,
        media=None,
        review_receipt=None,
    )
    with patch("cli_weapon.probe_armory") as probe:
        assert run_weapon(args, emit=lambda payload: print(json.dumps(payload))) == 0
    probe.assert_not_called()
    assert json.loads(capsys.readouterr().out)["status"] == "planned"


def test_promotion_requires_human_approval(tmp_path: Path) -> None:
    canary = tmp_path / "canary.json"
    review = tmp_path / "review.json"
    canary.write_text(json.dumps(_completed_canary()), encoding="utf-8")
    review.write_text(json.dumps({"status": "pending_human_review"}), encoding="utf-8")
    with pytest.raises(WeaponControlError, match="approved human review"):
        promotion_packet("ltx2-broll-pilot", canary, review)


def test_promotion_never_changes_default_provider(tmp_path: Path) -> None:
    canary = tmp_path / "canary.json"
    review = tmp_path / "review.json"
    sha = "deadbeef"
    canary.write_text(json.dumps(_completed_canary(sha=sha)), encoding="utf-8")
    review.write_text(
        json.dumps(
            {
                "status": "approved",
                "human_reviewed": True,
                "weapon_id": "ltx2-broll-pilot",
                "output_sha256": sha,
            }
        ),
        encoding="utf-8",
    )
    packet = promotion_packet("ltx2-broll-pilot", canary, review)
    assert packet["may_change_default_provider"] is False
    assert packet["status"] == "promotion_ready"
    assert packet["output_sha256"] == sha


def test_promotion_rejects_review_bound_to_other_bytes(tmp_path: Path) -> None:
    canary = tmp_path / "canary.json"
    review = tmp_path / "review.json"
    canary.write_text(json.dumps(_completed_canary(sha="aaa")), encoding="utf-8")
    review.write_text(
        json.dumps(
            {
                "status": "approved",
                "human_reviewed": True,
                "weapon_id": "ltx2-broll-pilot",
                "output_sha256": "bbb",
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(WeaponControlError, match="approved human review"):
        promotion_packet("ltx2-broll-pilot", canary, review)


def test_research_weapon_canary_is_plannable(capsys) -> None:
    args = Namespace(
        weapon_action="canary",
        weapon_id="ltx2-broll-pilot",
        base_url=None,
        execute=False,
        complete=False,
        confirm=False,
        workflow=None,
        timeout=60,
        receipt=None,
        submission_receipt=None,
        media=None,
        review_receipt=None,
    )
    assert run_weapon(args, emit=lambda payload: print(json.dumps(payload))) == 0
    assert json.loads(capsys.readouterr().out)["allowed_stage"] == "pilot"


def test_weapon_inventory_lists_primaries(capsys) -> None:
    args = Namespace(
        weapon_action="inventory",
        validate=False,
        primary_for=None,
        tier="primary",
        modality=None,
        receipt=None,
    )
    assert run_weapon(args, emit=lambda payload: print(json.dumps(payload))) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["kind"] == "ai-film-weapon-inventory-report"
    assert out["ok"] is True
    assert out["line"]
    assert "still" in out["primaries"]
    assert "motion" in out["primaries"]
    assert any(e["id"] == "minimax-h3-i2v-pilot" for e in out["entries"])


def test_weapon_inventory_primary_for_i2v(capsys) -> None:
    args = Namespace(
        weapon_action="inventory",
        validate=True,
        primary_for="image-to-video",
        tier=None,
        modality=None,
        receipt=None,
    )
    assert run_weapon(args, emit=lambda payload: print(json.dumps(payload))) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True
    assert out["primary_for"]["id"] == "minimax-h3-i2v-pilot"
    assert out["validation"]["ok"] is True

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


def test_canary_is_a_plan_without_execute_or_remote_submission(capsys) -> None:
    args = Namespace(
        weapon_action="canary",
        weapon_id="wan22-i2v-quality",
        base_url="http://127.0.0.1:18188",
        execute=False,
        confirm=False,
        workflow=None,
        timeout=60,
        receipt=None,
    )
    with patch("cli_weapon.probe_armory") as probe:
        assert run_weapon(args, emit=lambda payload: print(json.dumps(payload))) == 0
    probe.assert_not_called()
    assert json.loads(capsys.readouterr().out)["status"] == "planned"


def test_promotion_requires_human_approval(tmp_path: Path) -> None:
    canary = tmp_path / "canary.json"
    review = tmp_path / "review.json"
    canary.write_text(json.dumps({"weapon_id": "ltx2-broll-pilot", "status": "completed"}))
    review.write_text(json.dumps({"status": "pending_human_review"}))
    with pytest.raises(WeaponControlError, match="approved human review"):
        promotion_packet("ltx2-broll-pilot", canary, review)


def test_promotion_never_changes_default_provider(tmp_path: Path) -> None:
    canary = tmp_path / "canary.json"
    review = tmp_path / "review.json"
    canary.write_text(json.dumps({"weapon_id": "ltx2-broll-pilot", "status": "completed"}))
    review.write_text(json.dumps({"status": "approved", "human_reviewed": True}))
    packet = promotion_packet("ltx2-broll-pilot", canary, review)
    assert packet["may_change_default_provider"] is False
    assert packet["status"] == "promotion_ready"

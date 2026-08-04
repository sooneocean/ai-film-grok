"""Wave W8: autopilot local throughput allowlist (closeout / preflight / variety)."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from advance import ADVANCE_ACTIONS, AdvanceError, _validate_argv  # noqa: E402
from autopilot import LOCAL_THROUGHPUT_NEXT_IDS, autopilot_once  # noqa: E402
from review_control import update_settings  # noqa: E402


def _enable(root: Path) -> None:
    update_settings(
        root,
        expected_revision=0,
        budget_envelopes={"motion": 100},
        autopilot={"enabled": True, "allowed_providers": ["grok"]},
    )


def _local_packet(root: Path, *, next_id: str, argv: list[str], skill_id: str) -> dict:
    return {
        "next_id": next_id,
        "next_action": {
            "transaction_id": f"tx-local-{next_id}",
            "operation": argv[0],
            "approval_class": "none",
            "spend_class": "local",
            "skill_id": skill_id,
            "argv": argv,
        },
    }


def test_w8_throughput_ids_are_on_advance_allowlist() -> None:
    missing = sorted(LOCAL_THROUGHPUT_NEXT_IDS - set(ADVANCE_ACTIONS))
    assert missing == [], f"W8 ids missing from ADVANCE_ACTIONS: {missing}"


def test_w8_core_ops_validate_argv(tmp_path: Path) -> None:
    root = tmp_path.resolve()
    cases = (
        (
            "bulk-preflight",
            ["bulk-preflight", "--root", str(root), "--no-tunnel"],
            "image.animate",
        ),
        ("variety-precheck", ["variety-precheck", "--root", str(root)], "story.validate"),
        ("closeout-run", ["closeout", "run", "--root", str(root)], "projection.verify"),
        ("pilot-pack", ["pilot-pack", "--root", str(root)], "quality.inspect"),
        ("select-shortlist", ["select-shortlist", "--root", str(root)], "projection.verify"),
        ("gate-auto", ["gate-auto", "--root", str(root)], "projection.verify"),
        ("ship-prep", ["ship-prep", "--root", str(root)], "projection.verify"),
    )
    for next_id, argv, skill_id in cases:
        _validate_argv(
            root=root,
            action_id=next_id,
            action={
                "spend_class": "local",
                "approval_class": "none",
                "skill_id": skill_id,
                "argv": argv,
            },
        )


def test_w8_agent_review_final_rejects_apply_flag(tmp_path: Path) -> None:
    root = tmp_path.resolve()
    try:
        _validate_argv(
            root=root,
            action_id="agent-review-final",
            action={
                "spend_class": "local",
                "approval_class": "none",
                "skill_id": "quality.inspect",
                "argv": [
                    "agent-review-final",
                    "--root",
                    str(root),
                    "--apply",
                    "--reviewer",
                    "dex",
                    "--user-phrase",
                    "可以",
                ],
            },
        )
    except AdvanceError as exc:
        assert "unknown or incomplete advance flag" in str(exc)
        assert "--apply" in str(exc) or "apply" in str(exc).lower()
    else:
        raise AssertionError("expected --apply to be rejected by advance policy")


def test_autopilot_dry_run_plans_local_throughput_without_advance(tmp_path: Path) -> None:
    _enable(tmp_path)
    root = tmp_path.resolve()
    packet = _local_packet(
        root,
        next_id="variety-precheck",
        argv=["variety-precheck", "--root", str(root)],
        skill_id="story.validate",
    )
    with (
        patch("autopilot.build_dispatch", return_value=packet),
        patch("advance.advance_local") as advance_mock,
    ):
        report = autopilot_once(
            tmp_path,
            max_actions=1,
            dry_run=True,
            skill_executor=lambda *_a, **_k: (_ for _ in ()).throw(
                AssertionError("must not run skill")
            ),
            notifier=lambda _: {"attempted": False},
        )
    assert report["dry_run"] is True
    assert report["executed"]
    row = report["executed"][0]
    assert row["kind"] == "local"
    assert row["dry_run"] is True
    assert row["next_id"] == "variety-precheck"
    assert row["w8_throughput"] is True
    advance_mock.assert_not_called()


def test_autopilot_executes_local_via_advance_local(tmp_path: Path) -> None:
    _enable(tmp_path)
    root = tmp_path.resolve()
    packet = _local_packet(
        root,
        next_id="bulk-preflight",
        argv=["bulk-preflight", "--root", str(root), "--no-tunnel"],
        skill_id="image.animate",
    )
    local_report = {"ok": True, "executed_count": 1, "stop_reason": "max_local_reached"}

    with (
        patch("autopilot.build_dispatch", return_value=packet),
        patch("advance.advance_local", return_value=local_report) as advance_mock,
        patch(
            "autopilot.build_verification_report",
            return_value={"ok": True, "blocking_checks": []},
        ),
    ):
        report = autopilot_once(
            tmp_path,
            max_actions=1,
            skill_executor=lambda *_a, **_k: (_ for _ in ()).throw(
                AssertionError("must not run skill")
            ),
            notifier=lambda _: {"attempted": False},
        )
    advance_mock.assert_called_once()
    assert report["executed"][0]["kind"] == "local"
    assert report["executed"][0]["next_id"] == "bulk-preflight"
    assert report["executed"][0]["w8_throughput"] is True
    assert report["executed"][0]["report"]["executed_count"] == 1


def test_autopilot_stops_when_local_next_not_on_advance(tmp_path: Path) -> None:
    _enable(tmp_path)
    root = tmp_path.resolve()
    packet = {
        "next_id": "tunnel-probe",  # local/none in dispatch, not on ADVANCE_ACTIONS
        "next_action": {
            "transaction_id": "tx-tunnel",
            "operation": "tunnel-probe",
            "approval_class": "none",
            "spend_class": "local",
            "skill_id": "dispatch.orchestrate",
            "argv": ["tunnel-probe", "--root", str(root)],
        },
    }
    with patch("autopilot.build_dispatch", return_value=packet):
        report = autopilot_once(
            tmp_path,
            max_actions=1,
            skill_executor=lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("must not run")),
            notifier=lambda _: {"attempted": False},
        )
    assert report["stop_reason"] == "local_not_allowlisted"
    assert "tunnel-probe" in report["stop_detail"]
    assert report["executed"] == []


def test_autopilot_still_stops_on_human_review_final(tmp_path: Path) -> None:
    _enable(tmp_path)
    packet = {
        "next_id": "review-final",
        "next_action": {
            "transaction_id": "tx-rf",
            "operation": "review-final",
            "approval_class": "human_required",
            "spend_class": "local",
            "skill_id": "quality.inspect",
            "argv": ["review-final", "--root", str(tmp_path.resolve()), "--approve"],
        },
    }
    with patch("autopilot.build_dispatch", return_value=packet):
        report = autopilot_once(
            tmp_path,
            max_actions=1,
            skill_executor=lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("must not run")),
            notifier=lambda _: {"attempted": False},
        )
    assert report["stop_reason"] == "human_approval_required"
    assert report["executed"] == []

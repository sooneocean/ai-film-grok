from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from autopilot import autopilot_once  # noqa: E402
from autopilot_notify import notify_telegram  # noqa: E402
from review_control import update_settings  # noqa: E402


def _enable(root: Path) -> None:
    update_settings(
        root,
        expected_revision=0,
        budget_envelopes={"motion": 100},
        autopilot={"enabled": True, "allowed_providers": ["grok"]},
    )


def _packet(root: Path, payload_path: Path) -> dict[str, object]:
    return {
        "next_action": {
            "transaction_id": "dispatch-tx-01",
            "operation": "skill",
            "approval_class": "human_required",
            "spend_class": "paid",
            "argv": [
                "skill",
                "run",
                "--skill-id",
                "image.animate",
                "--payload-file",
                str(payload_path),
            ],
        }
    }


def _payload(root: Path) -> Path:
    target = root / "request.json"
    target.write_text(
        json.dumps(
            {
                "skillId": "image.animate",
                "projectRoot": str(root),
                "nodeRef": "shot:01",
                "input": {"provider": "grok"},
                "spendScope": {
                    "shotIds": ["01"],
                    "candidateCount": 1,
                    "budget": {"maxUnits": 10, "currency": "usd_ticks"},
                },
            }
        ),
        encoding="utf-8",
    )
    return target


def test_autopilot_is_disabled_by_default_and_writes_a_receipt(tmp_path: Path) -> None:
    report = autopilot_once(tmp_path, notifier=lambda _: {"attempted": False})
    assert report["stop_reason"] == "autopilot_disabled"
    assert Path(report["receipt"]).is_file()


def test_autopilot_executes_only_budgeted_allowlisted_skill(tmp_path: Path) -> None:
    _enable(tmp_path)
    payload = _payload(tmp_path)
    calls: list[str] = []

    def execute(skill_id, path, *, dry_run=False):
        calls.append(skill_id)
        return {"ok": True, "transaction_id": "tx-test"}

    with patch("autopilot.build_dispatch", return_value=_packet(tmp_path, payload)):
        report = autopilot_once(
            tmp_path,
            max_actions=1,
            skill_executor=execute,
            notifier=lambda _: {"attempted": False},
            provider_ready=lambda *_: (True, "test"),
        )
    assert calls == ["image.animate"]
    assert report["executed"][0]["budget"]["stage"] == "motion"


def test_autopilot_stops_for_unknown_cost_or_unallowed_provider(tmp_path: Path) -> None:
    _enable(tmp_path)
    payload = _payload(tmp_path)
    (tmp_path / "receipts").mkdir(exist_ok=True)
    (tmp_path / "receipts" / "generation-usage.json").write_text(
        json.dumps({"events": [{"phase": "accepted", "operation": "i2v", "usage": {}}]}),
        encoding="utf-8",
    )
    with patch("autopilot.build_dispatch", return_value=_packet(tmp_path, payload)):
        report = autopilot_once(tmp_path, notifier=lambda _: {"attempted": False})
    assert report["stop_reason"] == "external_safety_gate"
    assert "cost is unknown" in report["stop_detail"]


def test_autopilot_rejects_fractional_usd_ticks_before_execution(tmp_path: Path) -> None:
    _enable(tmp_path)
    payload = _payload(tmp_path)
    request = json.loads(payload.read_text(encoding="utf-8"))
    request["spendScope"]["budget"]["maxUnits"] = 0.5
    payload.write_text(json.dumps(request), encoding="utf-8")

    with patch("autopilot.build_dispatch", return_value=_packet(tmp_path, payload)):
        report = autopilot_once(
            tmp_path,
            max_actions=1,
            skill_executor=lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("must not run")
            ),
            notifier=lambda _: {"attempted": False},
        )

    assert report["stop_reason"] == "external_safety_gate"
    assert "positive integer" in report["stop_detail"]


def test_autopilot_dry_run_never_authorizes_external_execution(tmp_path: Path) -> None:
    _enable(tmp_path)
    payload = _payload(tmp_path)
    calls: list[bool] = []

    def execute(_skill_id, _path, *, dry_run=False):
        calls.append(dry_run)
        return {"ok": True}

    with patch("autopilot.build_dispatch", return_value=_packet(tmp_path, payload)):
        report = autopilot_once(
            tmp_path,
            max_actions=1,
            dry_run=True,
            skill_executor=execute,
            notifier=lambda _: {"attempted": False},
            provider_ready=lambda *_: (True, "test"),
        )
    assert calls == [True]
    assert report["dry_run"] is True


def test_autopilot_reserves_budget_until_a_cost_receipt_arrives(tmp_path: Path) -> None:
    _enable(tmp_path)
    update_settings(tmp_path, expected_revision=1, budget_envelopes={"motion": 10})
    payload = _payload(tmp_path)
    with patch("autopilot.build_dispatch", return_value=_packet(tmp_path, payload)):
        first = autopilot_once(
            tmp_path,
            max_actions=1,
            skill_executor=lambda *_args, **_kwargs: {"ok": True},
            notifier=lambda _: {"attempted": False},
            provider_ready=lambda *_: (True, "test"),
        )
        second = autopilot_once(tmp_path, notifier=lambda _: {"attempted": False})
    assert first["executed"]
    assert second["stop_reason"] == "external_safety_gate"
    assert "budget is exhausted" in second["stop_detail"]


def test_autopilot_stops_for_each_completed_sample_batch(tmp_path: Path) -> None:
    _enable(tmp_path)
    (tmp_path / "receipts").mkdir(exist_ok=True)
    (tmp_path / "receipts" / "media-queue.json").write_text(
        json.dumps({"jobs": [{"status": "succeeded", "shot_id": f"s{i}"} for i in range(5)]}),
        encoding="utf-8",
    )
    report = autopilot_once(tmp_path, notifier=lambda _: {"attempted": False})
    assert report["stop_reason"] == "sample_review_required"
    assert "shot:s4" in report["stop_detail"]


def test_autopilot_never_submits_beside_unknown_queue_work(tmp_path: Path) -> None:
    _enable(tmp_path)
    payload = _payload(tmp_path)
    (tmp_path / "receipts").mkdir(exist_ok=True)
    (tmp_path / "receipts" / "media-queue.json").write_text(
        json.dumps({"jobs": [{"status": "unknown"}]}), encoding="utf-8"
    )
    calls: list[str] = []
    with patch("autopilot.build_dispatch", return_value=_packet(tmp_path, payload)):
        report = autopilot_once(
            tmp_path,
            skill_executor=lambda *_args, **_kwargs: calls.append("called") or {"ok": True},
            notifier=lambda _: {"attempted": False},
            provider_ready=lambda *_: (True, "test"),
        )
    assert calls == []
    assert report["stop_reason"] == "queue_unknown"


def test_autopilot_stops_immediately_after_a_quality_gate_failure(tmp_path: Path) -> None:
    _enable(tmp_path)
    payload = _payload(tmp_path)
    (tmp_path / "film-spec.json").write_text('{"shots": []}', encoding="utf-8")
    with (
        patch("autopilot.build_dispatch", return_value=_packet(tmp_path, payload)),
        patch(
            "autopilot.build_verification_report",
            return_value={"ok": False, "blocking_checks": ["scene_sound"]},
        ),
    ):
        report = autopilot_once(
            tmp_path,
            max_actions=2,
            skill_executor=lambda *_args, **_kwargs: {"ok": True},
            notifier=lambda _: {"attempted": False},
            provider_ready=lambda *_: (True, "test"),
        )
    assert report["stop_reason"] == "quality_gate_failed"
    assert report["stop_detail"] == "scene_sound"


def test_telegram_notification_is_optional_and_never_exposes_configuration(monkeypatch) -> None:
    monkeypatch.delenv("AIFILM_TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("AIFILM_TELEGRAM_CHAT_ID", raising=False)
    report = notify_telegram("needs review")
    assert report == {"attempted": False, "ok": False, "reason": "not_configured"}


def test_cli_autopilot_reports_safe_disabled_state(tmp_path: Path, capsys) -> None:
    from aifilm_grok import main

    assert main(["autopilot", "--root", str(tmp_path)]) == 0
    assert json.loads(capsys.readouterr().out)["stop_reason"] == "autopilot_disabled"

from __future__ import annotations

import fcntl
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from advance import AdvanceError, _redact, _validate_argv, advance_local  # noqa: E402


def _action(
    argv: list[str],
    *,
    skill_id: str = "dispatch.orchestrate",
    spend: str = "local",
    approval: str = "none",
) -> dict[str, object]:
    return {
        "skill_id": skill_id,
        "argv": argv,
        "spend_class": spend,
        "approval_class": approval,
    }


@pytest.mark.parametrize(
    ("action_id", "argv", "skill_id"),
    [
        ("pilot-approve", ["pilot", "approve"], "dispatch.orchestrate"),
        ("review-final", ["review-final", "--approve"], "quality.inspect"),
        ("grok-video", ["grok-oauth", "video"], "dispatch.orchestrate"),
        ("media", ["media-queue", "add"], "dispatch.orchestrate"),
        ("tts", ["tts-rehearse", "--backend", "edge"], "dispatch.orchestrate"),
        ("final", ["final"], "video.render"),
    ],
)
def test_sensitive_or_unknown_actions_are_never_allowlisted(
    tmp_path: Path,
    action_id: str,
    argv: list[str],
    skill_id: str,
) -> None:
    with pytest.raises(AdvanceError, match="not allowlisted"):
        _validate_argv(
            root=tmp_path,
            action_id=action_id,
            action=_action(argv, skill_id=skill_id),
        )


def test_allowlisted_action_rejects_forged_policy_and_control_characters(
    tmp_path: Path,
) -> None:
    root = tmp_path.resolve()
    safe = ["write-spec", "--root", str(root)]
    with pytest.raises(AdvanceError, match="local"):
        _validate_argv(
            root=root,
            action_id="write-spec",
            action=_action(safe, spend="paid"),
        )
    with pytest.raises(AdvanceError, match="control"):
        _validate_argv(
            root=root,
            action_id="write-spec",
            action=_action(["write-spec", "--root", str(root) + "\n/bin/sh"]),
        )


def test_allowlisted_action_rejects_root_replacement(tmp_path: Path) -> None:
    with pytest.raises(AdvanceError, match="authoritative"):
        _validate_argv(
            root=tmp_path.resolve(),
            action_id="write-spec",
            action=_action(["write-spec", "--root", str(tmp_path / "outside")]),
        )


def test_advance_executes_one_safe_local_action_then_stops_cycle(tmp_path: Path) -> None:
    (tmp_path / "brief.json").write_text('{"title":"t"}\n', encoding="utf-8")
    calls: list[list[str]] = []

    def fake_run(argv: list[str]) -> dict[str, object]:
        calls.append(list(argv))
        if argv[0] == "write-spec":
            (tmp_path / "film-spec.json").write_text(
                '{"title":"t","shots":[]}\n',
                encoding="utf-8",
            )
        return {"ok": True, "returncode": 0, "stdout": "", "stderr": ""}

    report = advance_local(
        tmp_path,
        gates={"brief": True, "style_locked": True},
        max_local=3,
        runner=fake_run,
    )
    assert report["executed_count"] == 1
    assert report["stop_reason"] in {"cycle_detected", "duplicate_transaction"}
    assert calls[0][0] == "write-spec"
    assert calls[1][0] == "preflight"


def test_advance_stops_before_human_or_external_action(tmp_path: Path) -> None:
    (tmp_path / "brief.json").write_text('{"title":"t"}\n', encoding="utf-8")
    (tmp_path / "film-spec.json").write_text(
        '{"title":"t","shots":[{"id":"shot01","nar":"x"}]}\n',
        encoding="utf-8",
    )
    calls: list[list[str]] = []

    def should_not_run(argv: list[str]) -> dict[str, object]:
        calls.append(argv)
        return {"ok": True}

    report = advance_local(
        tmp_path,
        gates={"brief": True, "style_locked": True, "spec": True},
        max_local=3,
        runner=should_not_run,
    )
    assert report["executed_count"] == 0
    assert report["stop_reason"] in {
        "human_approval_required",
        "unsafe_or_unknown_action",
        "no_executable_action",
    }
    assert calls == []


@pytest.mark.parametrize(
    ("next_id", "approval", "spend", "expected"),
    [
        ("pilot-approve", "human_required", "local", "human_approval_required"),
        ("grok-video", "none", "paid", "paid_or_external"),
        ("media-queue", "none", "external", "paid_or_external"),
    ],
)
def test_advance_explicitly_stops_at_pilot_paid_and_external_boundaries(
    tmp_path: Path,
    next_id: str,
    approval: str,
    spend: str,
    expected: str,
) -> None:
    packet = {
        "ok": True,
        "root": str(tmp_path),
        "schema_version": 2,
        "next_id": next_id,
        "next_action": _action(
            [next_id, "--root", str(tmp_path)],
            spend=spend,
            approval=approval,
        ),
    }
    with patch("advance.build_dispatch", return_value=packet):
        report = advance_local(tmp_path, max_local=1)
    assert report["executed_count"] == 0
    assert report["stop_reason"] == expected


def test_advance_stops_and_records_command_failure(tmp_path: Path) -> None:
    (tmp_path / "brief.json").write_text('{"title":"t"}\n', encoding="utf-8")

    def fail_action(argv: list[str]) -> dict[str, object]:
        return {"ok": False, "returncode": 7, "stdout": "", "stderr": "failed"}

    report = advance_local(
        tmp_path,
        gates={"brief": True, "style_locked": True},
        max_local=1,
        runner=fail_action,
    )
    assert report["ok"] is False
    assert report["stop_reason"] == "action_failed"
    assert report["executed"][0]["returncode"] == 7


def test_advance_stops_when_verification_fails(tmp_path: Path) -> None:
    (tmp_path / "brief.json").write_text('{"title":"t"}\n', encoding="utf-8")
    calls = 0

    def fail_verification(argv: list[str]) -> dict[str, object]:
        nonlocal calls
        calls += 1
        if calls == 1:
            (tmp_path / "film-spec.json").write_text(
                '{"title":"t","shots":[]}\n',
                encoding="utf-8",
            )
            return {"ok": True, "returncode": 0, "stdout": "", "stderr": ""}
        return {"ok": False, "returncode": 2, "stdout": "", "stderr": "invalid"}

    report = advance_local(
        tmp_path,
        gates={"brief": True, "style_locked": True},
        max_local=1,
        runner=fail_verification,
    )
    assert report["ok"] is False
    assert report["stop_reason"] == "verification_failed"
    assert report["executed"][0]["verification_ok"] is False


def test_advance_rejects_state_change_after_planning(tmp_path: Path) -> None:
    (tmp_path / "brief.json").write_text('{"title":"t"}\n', encoding="utf-8")
    with patch("advance.compute_state_hash", return_value="stale-state"):
        with pytest.raises(AdvanceError, match="state changed"):
            advance_local(
                tmp_path,
                gates={"brief": True, "style_locked": True},
                max_local=1,
                runner=lambda argv: {"ok": True},
            )


def test_advance_stops_on_completed_duplicate_transaction(tmp_path: Path) -> None:
    (tmp_path / "brief.json").write_text('{"title":"t"}\n', encoding="utf-8")
    with patch("advance.load_receipt", return_value={"state": "completed"}):
        report = advance_local(
            tmp_path,
            gates={"brief": True, "style_locked": True},
            max_local=1,
            runner=lambda argv: {"ok": True},
        )
    assert report["executed_count"] == 0
    assert report["stop_reason"] == "duplicate_transaction"


def test_advance_lock_is_non_blocking_and_secret_output_is_redacted(tmp_path: Path) -> None:
    receipts = tmp_path / "receipts"
    receipts.mkdir()
    lock_path = receipts / ".advance.lock"
    with lock_path.open("w", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(AdvanceError, match="already owns"):
            advance_local(tmp_path, max_local=1)
    redacted = _redact("Authorization: Bearer abc.def token=secret-value")
    assert "abc.def" not in redacted
    assert "secret-value" not in redacted
    assert redacted.count("[REDACTED]") == 2


def test_advance_receipt_never_contains_raw_runner_secret(tmp_path: Path) -> None:
    (tmp_path / "brief.json").write_text('{"title":"t"}\n', encoding="utf-8")

    def redacted_failure(argv: list[str]) -> dict[str, object]:
        return {
            "ok": False,
            "returncode": 1,
            "stdout": "token=top-secret",
            "stderr": "",
        }

    advance_local(
        tmp_path,
        gates={"brief": True, "style_locked": True},
        max_local=1,
        runner=redacted_failure,
    )
    receipt_paths = list((tmp_path / "receipts" / "transactions").glob("*.json"))
    assert len(receipt_paths) == 1
    receipt_text = receipt_paths[0].read_text(encoding="utf-8")
    assert "top-secret" not in receipt_text
    assert json.loads(receipt_text)["result"]["stdout"].endswith("[REDACTED]")


def test_max_local_has_hard_upper_bound(tmp_path: Path) -> None:
    with pytest.raises(AdvanceError, match="between 1 and 10"):
        advance_local(tmp_path, max_local=11)

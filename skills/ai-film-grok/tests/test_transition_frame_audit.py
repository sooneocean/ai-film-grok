from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import transition_frame_audit as audit  # noqa: E402
from util import sha256_file, write_json  # noqa: E402


def _operation() -> dict:
    return {
        "join_id": "s01__s02",
        "join_index": 0,
        "from_shot": "s01",
        "to_shot": "s02",
        "continuity_class": "continue",
        "picture": {"base": "hard_cut", "duration_sec": 0, "hyperframes_overlay": "none"},
        "qa": {"review_frames": [-2, 0, 2]},
    }


def _approve_template(template: dict) -> None:
    for decision in template["decisions"]:
        decision["status"] = "approved"
        decision["note"] = "动作衔接与字幕均正常"
    write_json(Path(template["path"]), template)


def test_review_timestamps_are_final_clock_frame_offsets() -> None:
    operation = _operation() | {"timeline": {"at_sec": 3.0}}
    assert audit.review_timestamps(operation, fps=24, duration_sec=10) == [2.917, 3.0, 3.083]


def test_bound_operations_adds_timing_for_legacy_delivery_receipt() -> None:
    report = {
        "transition": {"operations": [_operation()], "film_timeline": {"shot_starts": [0, 3]}}
    }
    assert audit.bound_operations(report)[0]["timeline"]["at_sec"] == 3.0


def test_bound_operations_rejects_decorated_continue_seam() -> None:
    operation = _operation()
    operation["picture"] = {
        "base": "xfade",
        "duration_sec": 0.5,
        "hyperframes_overlay": "light_leak",
    }
    report = {"transition": {"operations": [operation], "film_timeline": {"shot_starts": [0, 3]}}}
    with pytest.raises(ValueError, match="continue seam"):
        audit.bound_operations(report)


def test_build_audit_is_human_pending_and_hash_bound(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    final = tmp_path / "out" / "film_final.mp4"
    final.parent.mkdir(parents=True)
    final.write_bytes(b"final")
    write_json(
        tmp_path / "out" / "final-delivery.json",
        {
            "output_sha256": sha256_file(final),
            "fps": 24,
            "duration_sec": 8,
            "transition": {"operations": [_operation()], "film_timeline": {"shot_starts": [0, 3]}},
        },
    )

    def fake_run(command: list[str], **_: object) -> object:
        Path(command[-1]).write_bytes(b"frame")
        return type("Result", (), {"returncode": 0})()

    monkeypatch.setattr(audit.subprocess, "run", fake_run)
    report = audit.build_transition_frame_audit(tmp_path)

    assert report["state"] == "needs_human_transition_review"
    assert report["transition_count"] == 1
    assert [frame["timestamp_sec"] for frame in report["transitions"][0]["frames"]] == [
        2.917,
        3.0,
        3.083,
    ]


def test_build_audit_rejects_final_that_drifted_from_delivery(tmp_path: Path) -> None:
    final = tmp_path / "out" / "film_final.mp4"
    final.parent.mkdir(parents=True)
    final.write_bytes(b"different")
    write_json(tmp_path / "out" / "final-delivery.json", {"output_sha256": "stale"})
    with pytest.raises(ValueError, match="no longer matches"):
        audit.build_transition_frame_audit(tmp_path)


def test_transition_attestation_requires_current_complete_frames(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    final = tmp_path / "out" / "film_final.mp4"
    final.parent.mkdir(parents=True)
    final.write_bytes(b"final")
    write_json(
        tmp_path / "out" / "final-delivery.json",
        {
            "output_sha256": sha256_file(final),
            "fps": 24,
            "duration_sec": 8,
            "transition": {"operations": [_operation()], "film_timeline": {"shot_starts": [0, 3]}},
        },
    )

    def fake_run(command: list[str], **_: object) -> object:
        Path(command[-1]).write_bytes(b"frame")
        return type("Result", (), {"returncode": 0})()

    monkeypatch.setattr(audit.subprocess, "run", fake_run)
    audit.build_transition_frame_audit(tmp_path)
    template = audit.build_transition_review_template(tmp_path)
    _approve_template(template)
    attestation = audit.attest_transition_review(
        tmp_path, user_phrase="所有转场通过", decisions_path=Path(template["path"])
    )
    assert attestation["state"] == "human_transition_review_approved"
    assert audit.transition_review_evidence_status(tmp_path)["ok"] is True
    assert audit._human_transition_phrase("所有轉場通過") is True
    assert audit._human_transition_phrase("所有转场未通过") is False
    assert audit._human_transition_phrase("转场不能通过") is False
    assert audit._human_transition_phrase("不是所有轉場通過") is False
    with pytest.raises(ValueError, match="approval phrase"):
        audit.attest_transition_review(tmp_path, user_phrase="不通过")


@pytest.mark.parametrize("target", ("final", "delivery", "audit", "frame"))
def test_transition_attestation_invalidates_each_bound_evidence_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, target: str
) -> None:
    final = tmp_path / "out" / "film_final.mp4"
    final.parent.mkdir(parents=True)
    final.write_bytes(b"final")
    delivery = tmp_path / "out" / "final-delivery.json"
    write_json(
        delivery,
        {
            "output_sha256": sha256_file(final),
            "fps": 24,
            "duration_sec": 8,
            "transition": {"operations": [_operation()], "film_timeline": {"shot_starts": [0, 3]}},
        },
    )

    def fake_run(command: list[str], **_: object) -> object:
        Path(command[-1]).write_bytes(b"frame")
        return type("Result", (), {"returncode": 0})()

    monkeypatch.setattr(audit.subprocess, "run", fake_run)
    report = audit.build_transition_frame_audit(tmp_path)
    template = audit.build_transition_review_template(tmp_path)
    _approve_template(template)
    audit.attest_transition_review(
        tmp_path, user_phrase="所有转场通过", decisions_path=Path(template["path"])
    )
    if target == "final":
        final.write_bytes(b"changed-final")
    elif target == "delivery":
        delivery.write_bytes(b"changed-delivery")
    elif target == "audit":
        Path(report["path"]).write_bytes(b"changed-audit")
    else:
        Path(report["transitions"][0]["frames"][0]["path"]).write_bytes(b"changed-frame")
    assert audit.transition_review_evidence_status(tmp_path)["ok"] is False


def test_zero_transition_audit_can_be_attested(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    final = tmp_path / "out" / "film_final.mp4"
    final.parent.mkdir(parents=True)
    final.write_bytes(b"final")
    write_json(
        tmp_path / "out" / "final-delivery.json",
        {
            "output_sha256": sha256_file(final),
            "fps": 24,
            "duration_sec": 8,
            "transition": {"operations": [], "film_timeline": {"shot_starts": [0]}},
        },
    )
    monkeypatch.setattr(audit.subprocess, "run", lambda *_args, **_kwargs: None)
    report = audit.build_transition_frame_audit(tmp_path)
    assert report["transition_count"] == 0
    audit.attest_transition_review(tmp_path, user_phrase="所有转场通过")
    assert audit.transition_review_evidence_status(tmp_path)["ok"] is True


def test_transition_attestation_requires_every_join_decision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    final = tmp_path / "out" / "film_final.mp4"
    final.parent.mkdir(parents=True)
    final.write_bytes(b"final")
    write_json(
        tmp_path / "out" / "final-delivery.json",
        {
            "output_sha256": sha256_file(final),
            "fps": 24,
            "duration_sec": 8,
            "transition": {"operations": [_operation()], "film_timeline": {"shot_starts": [0, 3]}},
        },
    )

    def fake_run(command: list[str], **_: object) -> object:
        Path(command[-1]).write_bytes(b"frame")
        return type("Result", (), {"returncode": 0})()

    monkeypatch.setattr(audit.subprocess, "run", fake_run)
    audit.build_transition_frame_audit(tmp_path)
    template = audit.build_transition_review_template(tmp_path)
    with pytest.raises(ValueError, match="not approved"):
        audit.attest_transition_review(
            tmp_path, user_phrase="所有转场通过", decisions_path=Path(template["path"])
        )
    template["decisions"][0]["status"] = "approved"
    write_json(Path(template["path"]), template)
    with pytest.raises(ValueError, match="reviewer note"):
        audit.attest_transition_review(
            tmp_path, user_phrase="所有转场通过", decisions_path=Path(template["path"])
        )
    _approve_template(template)
    attestation = audit.attest_transition_review(
        tmp_path, user_phrase="所有转场通过", decisions_path=Path(template["path"])
    )
    assert attestation["decisions"][0]["status"] == "approved"

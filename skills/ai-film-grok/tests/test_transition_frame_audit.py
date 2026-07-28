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

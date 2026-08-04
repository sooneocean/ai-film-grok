"""FRW platform rate limit: image ≥30s, video ≥5min, shared durable state."""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from frw_rate_limit import (  # noqa: E402
    IMAGE_MIN_INTERVAL_S,
    VIDEO_MIN_INTERVAL_S,
    SubmitBudget,
    classify_frw_op,
    frw_rate_snapshot,
    peek_frw_rate_wait,
    wait_frw_rate_limit,
)


def test_classify_image_and_video_ops() -> None:
    assert classify_frw_op(["img2image", "--img-url", "x"]) == "image"
    assert classify_frw_op(["text2image", "--prompt", "x"]) == "image"
    assert classify_frw_op(["newvideo", "--model", "x"]) == "video"
    assert classify_frw_op(["img2video", "--img-url", "x"]) == "video"
    assert classify_frw_op(["upload", "--file-path", "x"]) is None
    assert classify_frw_op(["img2image-query", "--task-id", "1"]) is None
    assert classify_frw_op(["canary"]) is None


def test_peek_does_not_mutate(tmp_path: Path) -> None:
    state = tmp_path / "rate.json"
    assert peek_frw_rate_wait("image", now=1000.0, state_path=state) == 0.0
    assert not state.is_file()


def test_wait_enforces_30s_gap(tmp_path: Path) -> None:
    state = tmp_path / "rate.json"
    slept: list[float] = []

    def fake_sleep(s: float) -> None:
        slept.append(s)

    w1 = wait_frw_rate_limit(
        "image",
        now=1000.0,
        sleep_fn=fake_sleep,
        state_path=state,
        log=lambda _m: None,
    )
    assert w1 == 0.0
    assert slept == []

    w2 = wait_frw_rate_limit(
        "image",
        now=1010.0,  # 10s later
        sleep_fn=fake_sleep,
        state_path=state,
        log=lambda _m: None,
    )
    assert abs(w2 - 20.0) < 0.2
    assert slept and abs(slept[0] - 20.0) < 0.2


def test_snapshot_fields(tmp_path: Path) -> None:
    state = tmp_path / "rate.json"
    wait_frw_rate_limit(
        "image",
        now=5000.0,
        sleep_fn=lambda _s: None,
        state_path=state,
        log=lambda _m: None,
    )
    snap = frw_rate_snapshot(now=5005.0, state_path=state)
    assert snap["image_min_interval_s"] == IMAGE_MIN_INTERVAL_S
    assert snap["video_min_interval_s"] == VIDEO_MIN_INTERVAL_S
    assert snap["image_ready"] is False
    assert snap["image_wait_s"] >= 24.0


def test_submit_budget() -> None:
    b = SubmitBudget(1)
    b.take()
    try:
        b.take()
        raise AssertionError("expected budget exhausted")
    except RuntimeError as exc:
        assert "budget exhausted" in str(exc).lower()

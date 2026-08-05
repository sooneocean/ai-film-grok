"""P1 post: timeline single clock + post-doctor + mix partial reason codes."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from post_doctor import run_post_doctor  # noqa: E402
from render_final import write_final_mix_partial_receipt  # noqa: E402
from timeline_clock import (  # noqa: E402
    audit_timeline_clock,
    compare_starts,
    rewrite_timeline_from_film,
)
from util import write_json  # noqa: E402

pytestmark = pytest.mark.hotpath


def test_compare_starts_detects_dual_clock() -> None:
    film = [0.0, 6.0, 12.0, 18.0]
    vo = [0.0, 7.6, 11.0, 19.2]
    cmp = compare_starts(film, vo, eps=0.08)
    assert cmp["ok"] is False
    assert cmp["max_delta"] and cmp["max_delta"] > 1.0
    assert len(cmp["mismatches"]) >= 2


def test_compare_starts_ok_within_eps() -> None:
    a = [0.0, 6.0, 12.0]
    b = [0.0, 6.05, 11.97]
    assert compare_starts(a, b, eps=0.08)["ok"] is True


def test_audit_and_rewrite_timeline_clock(tmp_path: Path) -> None:
    write_json(
        tmp_path / "receipts" / "film_timeline.json",
        {
            "shot_starts": [0.0, 6.0, 12.0],
            "output_duration": 18.0,
        },
    )
    write_json(
        tmp_path / "timeline.json",
        {
            "shot_starts": [0.0, 7.6, 15.0],
            "shots": [
                {"id": "s01", "duration_sec": 7.6},
                {"id": "s02", "duration_sec": 7.4},
                {"id": "s03", "duration_sec": 6.0},
            ],
        },
    )
    audit = audit_timeline_clock(tmp_path, write=True)
    assert audit["dual_clock"] is True
    assert audit["ok"] is False
    assert "DUAL_TIMELINE_CLOCK" in str(audit.get("error") or "")

    out = rewrite_timeline_from_film(tmp_path)
    assert out["ok"] is True
    tl = json.loads((tmp_path / "timeline.json").read_text(encoding="utf-8"))
    assert tl["shot_starts"] == [0.0, 6.0, 12.0]
    assert tl["shots"][0]["start_sec"] == 0.0
    assert abs(tl["shots"][1]["start_sec"] - 6.0) < 1e-6


def test_post_doctor_flags_double_burn(tmp_path: Path) -> None:
    write_json(
        tmp_path / "receipts" / "post-route.json",
        {
            "kind": "post-route",
            "caption_path": "master_hf",
            "plate_subs": "burn",
        },
    )
    report = run_post_doctor(tmp_path, write=True)
    codes = {i["code"] for i in report["hard"]}
    assert "DOUBLE_BURN_RISK" in codes
    assert report["ok"] is False


def test_post_doctor_srt_overlap_hard(tmp_path: Path) -> None:
    out = tmp_path / "out"
    out.mkdir()
    (out / "final.srt").write_text(
        "1\n00:00:00,000 --> 00:00:02,000\n甲\n\n2\n00:00:01,500 --> 00:00:03,000\n乙\n\n",
        encoding="utf-8",
    )
    report = run_post_doctor(tmp_path, write=True)
    codes = {i["code"] for i in report["hard"]}
    assert "SRT_OVERLAP" in codes


def test_mix_partial_receipt_has_reason_code_and_tracks(tmp_path: Path) -> None:
    mixed = tmp_path / "audio" / "mixed.wav"
    mixed.parent.mkdir(parents=True)
    mixed.write_bytes(b"RIFF....")
    path = write_final_mix_partial_receipt(
        tmp_path,
        prior_sc="dynamic_eq",
        error="filter graph hang",
        mixed=mixed,
        error_type="TimeoutExpired",
        affected_tracks=["mx", "dx"],
    )
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["schema_version"] == 2
    assert data["reason_code"] == "sidechain_mix_failed_amix_fallback"
    assert data["affected_tracks"] == ["mx", "dx"]
    assert data["honest_limits"]
    assert data["error_type"] == "TimeoutExpired"
    assert data["partial"] is True

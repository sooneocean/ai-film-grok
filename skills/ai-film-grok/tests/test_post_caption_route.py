"""P0 post caption_path + pixel check contracts (2026-08-05)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest import mock

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from caption_pixel_check import (  # noqa: E402
    caption_pixel_status,
    evidence_stale_after_final,
    run_caption_pixel_check,
)
from post_route import (  # noqa: E402
    PostRouteError,
    apply_route_to_plate,
    resolve_caption_path,
    write_post_route,
)
from util import write_json  # noqa: E402

pytestmark = pytest.mark.hotpath


def test_default_caption_path_from_engine() -> None:
    assert resolve_caption_path("/tmp", post_engine="hyperframes")["caption_path"] == "master_hf"
    assert resolve_caption_path("/tmp", post_engine="ffmpeg")["caption_path"] == "ship_hardburn"


def test_explicit_ship_overrides_hf_default(tmp_path: Path) -> None:
    r = resolve_caption_path(tmp_path, post_engine="hyperframes", explicit="ship_hardburn")
    assert r["caption_path"] == "ship_hardburn"
    assert r["plate_subs"] == "burn"
    assert r["allow_burned_underlay"] is True
    assert r["designed_caption_owner"] is False


def test_master_hf_forbids_plate_burn() -> None:
    route = {
        "caption_path": "master_hf",
        "post_engine": "hyperframes",
        "plate_cards": "blank",
        "designed_caption_owner": True,
        "allow_burned_underlay": False,
    }
    with pytest.raises(PostRouteError, match="forbids plate"):
        apply_route_to_plate(route, subs_mode="burn", plate_cards="blank")


def test_ship_forces_burn_when_subs_off() -> None:
    route = {
        "caption_path": "ship_hardburn",
        "post_engine": "ffmpeg",
        "plate_cards": "text",
        "designed_caption_owner": False,
        "allow_burned_underlay": False,
    }
    plate = apply_route_to_plate(route, subs_mode="off", plate_cards="auto")
    assert plate["subs"] == "burn"


def test_write_post_route_receipt(tmp_path: Path) -> None:
    route = resolve_caption_path(tmp_path, post_engine="hyperframes")
    out = write_post_route(tmp_path, route)
    path = tmp_path / "receipts" / "post-route.json"
    assert path.is_file()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["kind"] == "post-route"
    assert data["caption_path"] == "master_hf"
    assert out["path"] == str(path)


def test_caption_pixel_missing_final_is_red(tmp_path: Path) -> None:
    report = run_caption_pixel_check(tmp_path, write=True)
    assert report["ok"] is False
    assert report["missing_ink"] is True
    assert (tmp_path / "receipts" / "caption-pixel-check.json").is_file()


def test_caption_pixel_uses_probe(tmp_path: Path) -> None:
    final = tmp_path / "out" / "film_final.mp4"
    srt = tmp_path / "out" / "final.srt"
    final.parent.mkdir(parents=True)
    final.write_bytes(b"fake-mp4")
    srt.write_text(
        "1\n00:00:01,000 --> 00:00:03,000\n你好\n\n",
        encoding="utf-8",
    )
    fake_probe = {
        "ok": True,
        "likely_count": 3,
        "sample_count": 3,
        "samples": [
            {"ts": 1.0, "ok": True, "likely_caption_bar": True, "contrast": 80, "mean": 40},
            {"ts": 2.0, "ok": True, "likely_caption_bar": True, "contrast": 70, "mean": 50},
            {"ts": 3.0, "ok": True, "likely_caption_bar": True, "contrast": 90, "mean": 30},
        ],
    }
    with mock.patch(
        "final_stages.sample_bottom_band_activity",
        return_value=fake_probe,
    ):
        report = run_caption_pixel_check(tmp_path, write=True)
    assert report["ok"] is True
    assert report["missing_ink"] is False
    status = caption_pixel_status(tmp_path)
    assert status["ok"] is True
    assert status["stale"] is False


def test_caption_pixel_stale_when_final_changes(tmp_path: Path) -> None:
    final = tmp_path / "out" / "film_final.mp4"
    srt = tmp_path / "out" / "final.srt"
    final.parent.mkdir(parents=True)
    final.write_bytes(b"v1")
    srt.write_text("1\n00:00:01,000 --> 00:00:02,000\n字\n\n", encoding="utf-8")
    with mock.patch(
        "final_stages.sample_bottom_band_activity",
        return_value={"ok": True, "likely_count": 1, "sample_count": 1, "samples": []},
    ):
        run_caption_pixel_check(tmp_path, write=True)
    final.write_bytes(b"v2-changed")
    status = caption_pixel_status(tmp_path)
    assert status["stale"] is True
    assert status["ok"] is False


def test_evidence_stale_quality_report(tmp_path: Path) -> None:
    final = tmp_path / "out" / "film_final.mp4"
    final.parent.mkdir(parents=True)
    final.write_bytes(b"final-bytes")
    from util import sha256_file

    write_json(
        tmp_path / "out" / "quality-report.json",
        {"media_sha256": "deadbeef", "final_sha256": "deadbeef"},
    )
    # also write matching-looking caption receipt with wrong hash
    write_json(
        tmp_path / "receipts" / "caption-pixel-check.json",
        {
            "kind": "caption-pixel-check",
            "ok": True,
            "final": {"sha256": "old"},
            "subtitles": {"sha256": None},
        },
    )
    (tmp_path / "out" / "final.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\nx\n", encoding="utf-8")
    ev = evidence_stale_after_final(tmp_path)
    assert ev["ok"] is False
    codes = {i["code"] for i in ev["issues"]}
    assert "QUALITY_REPORT_STALE" in codes
    assert sha256_file(final) == ev["final_sha256"]


def test_closeout_includes_caption_pixel_step(tmp_path: Path) -> None:
    from closeout import closeout_status

    # no final → caption step soft-skipped (does not block before plate exists)
    status = closeout_status(tmp_path)
    ids = [s["id"] for s in status["steps"]]
    assert "caption_pixel" in ids
    assert "evidence_fresh" in ids
    cap = next(s for s in status["steps"] if s["id"] == "caption_pixel")
    assert cap.get("skipped") is True
    assert cap["ok"] is True

    # with final on disk but no pixel receipt → hard red
    out = tmp_path / "out"
    out.mkdir(parents=True)
    (out / "film_final.mp4").write_bytes(b"fake")
    (out / "final.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\n字\n", encoding="utf-8")
    status2 = closeout_status(tmp_path)
    cap2 = next(s for s in status2["steps"] if s["id"] == "caption_pixel")
    assert cap2.get("skipped") is not True
    assert cap2["ok"] is False

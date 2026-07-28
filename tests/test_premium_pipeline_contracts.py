from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(
    0, str(Path(__file__).resolve().parents[1] / "skills" / "ai-film-grok" / "scripts")
)

from dailies import dailies_status, update_dailies
from delivery_package import build_delivery_package
from post_quality import (
    audio_delivery_gate,
    premium_master_qc,
    register_vfx_shot,
    vfx_gate,
)
from provider_canary import canary_status, record_canary


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def test_provider_canary_is_hash_bound(tmp_path: Path) -> None:
    output = tmp_path / "pilot.mp4"
    output.write_bytes(b"real media placeholder")
    report = record_canary(
        tmp_path,
        provider="grok",
        output=str(output),
        reviewer="dex",
        identity_ok=True,
        motion_ok=True,
    )
    assert report["ok"] is True
    assert canary_status(tmp_path)["ok"] is True
    output.write_bytes(b"changed")
    assert canary_status(tmp_path)["ok"] is False


def test_dailies_budget_and_stale_candidate(tmp_path: Path) -> None:
    media = tmp_path / "shot01.mp4"
    media.write_bytes(b"candidate")
    report = update_dailies(
        tmp_path,
        shot_id="shot01",
        candidate=str(media),
        status="select",
        reviewer="dex",
        notes="approved",
        approved_budget=1,
    )
    assert report["ok"] is True
    assert dailies_status(tmp_path)["ok"] is True
    alternate = tmp_path / "shot01-alt.mp4"
    alternate.write_bytes(b"alternate")
    with pytest.raises(ValueError, match="budget exhausted"):
        update_dailies(
            tmp_path,
            shot_id="shot01",
            candidate=str(alternate),
            status="alternate",
            reviewer="dex",
            notes="",
            approved_budget=1,
        )
    media.write_bytes(b"changed")
    assert dailies_status(tmp_path)["ok"] is False


def test_vfx_and_audio_fail_closed(tmp_path: Path) -> None:
    plate = tmp_path / "plate.mov"
    plate.write_bytes(b"plate")
    assert vfx_gate(tmp_path)["ok"] is False
    register_vfx_shot(
        tmp_path, shot_id="shot01", plate=str(plate), status="approved", reviewer="dex"
    )
    assert vfx_gate(tmp_path)["ok"] is True
    assert audio_delivery_gate(tmp_path)["ok"] is False


def test_premium_master_qc_requires_caption_vfx_audio(tmp_path: Path) -> None:
    out = tmp_path / "out" / "film_final.mp4"
    out.parent.mkdir(parents=True)
    # ffprobe/readback is intentionally tested by integration smoke; this unit test verifies fail-closed receipts.
    out.write_bytes(b"not a video")
    report = premium_master_qc(tmp_path)
    assert report["ok"] is False
    codes = {item["code"] for item in report["blockers"]}
    assert "CAPTION_BURN_MISSING" in codes


def test_delivery_package_records_hash_bound_contract(tmp_path: Path) -> None:
    report = build_delivery_package(tmp_path, allow_missing=True)
    assert report["ok"] is True
    assert report["kind"] == "premium-delivery-package"
    assert (tmp_path / "receipts" / "premium-delivery-package.json").is_file()

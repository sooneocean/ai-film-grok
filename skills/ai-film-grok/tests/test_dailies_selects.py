from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from dailies_selects import (  # noqa: E402
    DailiesError,
    read_dailies,
    record_take,
    set_take_state,
)


def test_dailies_keeps_exact_take_shot_hash_and_director_notes(tmp_path: Path) -> None:
    record_take(
        tmp_path,
        take_id="take-001",
        shot_id="shot-010",
        asset_ref="clips/shot-010-t1.mp4",
        asset_hash="a" * 64,
        director_notes="performance holds through the turn",
    )
    set_take_state(
        tmp_path,
        take_id="take-001",
        state="select",
        director_notes="hero take for rough cut",
    )

    ledger = read_dailies(tmp_path)
    assert ledger["takes"]["take-001"]["shot_id"] == "shot-010"
    assert ledger["takes"]["take-001"]["state"] == "select"
    assert ledger["takes"]["take-001"]["asset_hash"] == "a" * 64
    assert len(ledger["events"]) == 2


def test_reject_requires_rejection_reason_and_never_deletes_take(tmp_path: Path) -> None:
    record_take(
        tmp_path,
        take_id="take-002",
        shot_id="shot-010",
        asset_ref="clips/shot-010-t2.mp4",
        asset_hash="b" * 64,
        director_notes="identity drift at tail",
    )

    with pytest.raises(DailiesError, match="rejection"):
        set_take_state(
            tmp_path,
            take_id="take-002",
            state="reject",
            director_notes="not usable",
        )

    set_take_state(
        tmp_path,
        take_id="take-002",
        state="reject",
        director_notes="do not promote",
        rejection_notes="wardrobe changes after frame 80",
    )
    assert "take-002" in read_dailies(tmp_path)["takes"]


def test_take_ids_are_unique_and_states_are_closed(tmp_path: Path) -> None:
    kwargs = dict(
        take_id="take-003",
        shot_id="shot-011",
        asset_ref="clips/shot-011-t1.mp4",
        asset_hash="c" * 64,
        director_notes="first review",
    )
    record_take(tmp_path, **kwargs)
    with pytest.raises(DailiesError, match="already exists"):
        record_take(tmp_path, **kwargs)
    with pytest.raises(DailiesError, match="raw\\|select\\|alternate\\|reject"):
        set_take_state(
            tmp_path,
            take_id="take-003",
            state="maybe",
            director_notes="invalid state",
        )

"""StillSource single resolver + peak cast-master forbid."""

from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from still_source import (  # noqa: E402
    audit_film_still_sources,
    is_peak_forbidden_cast_master,
    resolve_still_source,
)


def _png(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 48)
    return path


def _film(tmp_path: Path) -> Path:
    root = tmp_path / "film"
    root.mkdir()
    (root / "film-spec.json").write_text(
        json.dumps(
            {
                "title": "ss",
                "scenes": [
                    {
                        "id": "sc1",
                        "shots": [
                            {
                                "id": "s_peak",
                                "wardrobe_state": "bare",
                                "heat_phase": "act",
                                "cast_id": "hero",
                                "dramatic_function": "action",
                            },
                            {
                                "id": "s_setup",
                                "wardrobe_state": "full",
                                "heat_phase": "setup",
                                "cast_id": "hero",
                                "dramatic_function": "hook",
                            },
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return root


def test_approved_still_wins(tmp_path: Path) -> None:
    root = _film(tmp_path)
    still = _png(root / "stills" / "s_peak.png")
    (root / "manifest.json").write_text(
        json.dumps({"stills": {"s_peak": {"path": str(still), "status": "approved"}}}),
        encoding="utf-8",
    )
    entry = resolve_still_source(
        root,
        "s_peak",
        shot={"id": "s_peak", "wardrobe_state": "bare", "heat_phase": "act"},
    )
    assert entry["ok"] is True
    assert entry["path"] == str(still.resolve())
    assert entry["sha256"]
    assert entry["source"] == "approved"


def test_continue_handoff_beats_approved(tmp_path: Path) -> None:
    root = _film(tmp_path)
    still = _png(root / "stills" / "s_peak.png")
    end = _png(root / "receipts" / "continue-handoff" / "prev_end.png")
    entry = resolve_still_source(
        root,
        "s_peak",
        shot={"id": "s_peak", "chain_mode": "continue", "wardrobe_state": "bare"},
        approved_still=still,
        continue_end_frame=end,
        wants_continue=True,
    )
    assert entry["source"] == "continue_handoff"
    assert entry["path"] == str(end.resolve())


def test_peak_cast_master_blocked(tmp_path: Path) -> None:
    root = _film(tmp_path)
    cast = _png(root / "canonical" / "cast" / "hero.png")
    shot = {"id": "s_peak", "wardrobe_state": "bare", "heat_phase": "act"}
    assert is_peak_forbidden_cast_master(cast, shot) is True
    entry = resolve_still_source(
        root,
        "s_peak",
        shot=shot,
        still_override=cast,
    )
    assert entry["blocked"] is True
    assert entry["block_reason"] == "PEAK_CAST_MASTER_FORBIDDEN"


def test_state_photo_when_no_keyframe(tmp_path: Path) -> None:
    root = _film(tmp_path)
    state = _png(root / "canonical" / "cast-states" / "hero" / "bare.png")
    bible = {
        "schema_version": 2,
        "cast_state_masters": {"hero": {"bare": str(state.relative_to(root))}},
        "cast_masters": {},
    }
    (root / "style-bible.json").write_text(json.dumps(bible), encoding="utf-8")
    entry = resolve_still_source(
        root,
        "s_peak",
        shot={"id": "s_peak", "wardrobe_state": "bare", "cast_id": "hero"},
        kind="i2v",
    )
    assert entry["ok"] is True
    assert "state_photo" in str(entry["source"])
    assert entry["path"] == str(state.resolve())


def test_audit_peak_missing(tmp_path: Path) -> None:
    root = _film(tmp_path)
    # no stills — peak should be hard
    report = audit_film_still_sources(root)
    assert report["ok"] is False
    assert "s_peak" in report["peak_missing"]

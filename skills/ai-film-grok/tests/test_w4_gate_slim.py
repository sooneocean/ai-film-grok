"""W4 · gate slim: machine single-next, pilot H3 mode trio, ship-prep human one-pager."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from gate_auto import next_machine_lane_action  # noqa: E402
from pilot_pack import _go_template, _h3_mode_trio, pilot_pack  # noqa: E402
from util import write_json  # noqa: E402


def test_h3_mode_trio_picks_env_t2v(tmp_path: Path) -> None:
    write_json(
        tmp_path / "film-spec.json",
        {
            "_i2v_profile": "h3_primary",
            "h3": {"enabled": True},
            "scenes": [
                {
                    "shots": [
                        {
                            "id": "env1",
                            "shot_role": "env",
                            "dramatic_function": "bridge",
                        },
                        {
                            "id": "hero1",
                            "shot_role": "hero",
                            "heat_phase": "setup",
                            "dramatic_function": "hook",
                        },
                    ]
                }
            ],
        },
    )
    (tmp_path / "stills").mkdir()
    (tmp_path / "stills" / "hero1.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 8)
    trio = _h3_mode_trio(
        tmp_path,
        json.loads((tmp_path / "film-spec.json").read_text(encoding="utf-8")),
        ["hero1", "env1"],
    )
    assert trio.get("h3_enabled") is True
    assert trio.get("picks", {}).get("t2v") == "env1"
    tpl = _go_template(tmp_path, ["hero1", "env1"], h3_trio=trio)
    assert "h3 run" in tpl or "until-empty" in tpl


def test_pilot_pack_includes_h3_mode_trio(tmp_path: Path) -> None:
    write_json(
        tmp_path / "film-spec.json",
        {
            "title": "w4",
            "aspect_ratio": "9:16",
            "_i2v_profile": "h3_primary",
            "h3": {"enabled": True},
            "heat_scale": "soft",
            "vo_mode": "storyteller",
            "scenes": [
                {
                    "shots": [
                        {
                            "id": "s01",
                            "shot_role": "hero",
                            "nar": "hi",
                            "duration_sec": 4,
                            "dramatic_function": "hook",
                            "dsl": {
                                "action": "looks",
                                "motion": "eyes lift",
                                "visible_change": "down→up",
                            },
                        }
                    ]
                }
            ],
        },
    )
    with (
        mock.patch(
            "pilot_review.pilot_report",
            return_value={
                "shots": ["s01"],
                "suggested_shots": ["s01"],
                "all_media_ready": False,
                "scorecard_all_pass": False,
                "ready_count": 0,
                "media": {},
            },
        ),
        mock.patch("pilot_review.pick_pilot_shots", return_value=["s01"]),
        mock.patch("production_gates.load_pilot_approval", return_value={}),
        mock.patch("production_gates.pilot_is_user_approved", return_value=False),
    ):
        pack = pilot_pack(tmp_path, shots=["s01"])
    assert "h3_mode_trio" in pack
    assert pack.get("schema_version") == 2
    assert (tmp_path / "receipts" / "pilot-go.json").is_file()


def test_ship_prep_writes_human_one_pager(tmp_path: Path) -> None:
    from workflow_pack import ship_prep

    write_json(tmp_path / "film-spec.json", {"heat_scale": "soft", "scenes": [{"shots": []}]})
    write_json(tmp_path / "manifest.json", {"clips": {}})
    takes = tmp_path / "takes" / "s01"
    takes.mkdir(parents=True)
    (takes / "a.mp4").write_bytes(b"\x00" * 1000)
    (takes / "b.mp4").write_bytes(b"\x00" * 1000)

    with (
        mock.patch("workflow_pack.variety_precheck", return_value={"ok": True}),
        mock.patch(
            "workflow_pack.select_shortlist",
            return_value={"shots": [{"id": "s01"}], "promoted": []},
        ),
        mock.patch(
            "h3_fill_idle.pk_compare",
            return_value={
                "shots": [
                    {
                        "shot_id": "s01",
                        "take_count": 2,
                        "recommended": {
                            "lane": "h3",
                            "mean": 12.0,
                            "path": str(takes / "a.mp4"),
                            "pk_score": 1.0,
                        },
                        "caution": [],
                    }
                ],
                "dailies_path": str(tmp_path / "receipts" / "pk-dailies.md"),
            },
        ),
        mock.patch(
            "h3_fill_idle.next_fill_idle_job",
            return_value={"pending_count": 0, "next": None},
        ),
    ):
        rep = ship_prep(tmp_path, measure=False, promote=True, skip_variety=True)

    assert rep.get("human_pk_required") or rep.get("promote_deferred_human_pk")
    pager = tmp_path / "receipts" / "ship-prep-human.md"
    if rep.get("human_pk_required") or rep.get("promote_deferred_human_pk"):
        assert pager.is_file() or rep.get("human_one_pager")
        if pager.is_file():
            assert "select-shortlist" in pager.read_text(encoding="utf-8")


def test_next_actions_single_machine_when_clips_done(tmp_path: Path) -> None:
    from next_actions import build_next_actions

    write_json(tmp_path / "brief.json", {"title": "t"})
    write_json(
        tmp_path / "film-spec.json",
        {"title": "t", "scenes": [{"shots": [{"id": "s01", "duration_sec": 4}]}]},
    )
    write_json(
        tmp_path / "style-bible.json",
        {"locked": True, "signature": "x", "canonical_refs": ["a"]},
    )
    write_json(
        tmp_path / "manifest.json",
        {
            "clips": {
                "s01": {"status": "approved", "path": "clips/s01.mp4", "sha256": "abc"}
            }
        },
    )
    (tmp_path / "clips").mkdir()
    (tmp_path / "clips" / "s01.mp4").write_bytes(b"\x00" * 50)

    with mock.patch(
        "gate_auto.next_machine_lane_action",
        return_value={
            "id": "gate-auto",
            "cmd": f'aifilm gate-auto --root "{tmp_path}"',
            "why": "machine",
        },
    ):
        actions = build_next_actions(
            tmp_path,
            gates={
                "brief": True,
                "style_locked": True,
                "spec": True,
                "clips_complete": True,
                "final_complete": False,
            },
        )
    ids = [a.get("id") for a in actions]
    assert "gate-auto" in ids
    assert "select-shortlist" not in ids
    assert "final" not in ids


def test_next_machine_lane_prefers_ship_prep_multi(tmp_path: Path) -> None:
    takes = tmp_path / "takes" / "s01"
    takes.mkdir(parents=True)
    (takes / "a.mp4").write_bytes(b"x")
    (takes / "b.mp4").write_bytes(b"y")
    lane = next_machine_lane_action(tmp_path, prefer_ship_prep=True)
    assert lane is not None
    assert lane["id"] == "ship-prep"

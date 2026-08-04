"""Fill-Idle queue: priority P0→P1→P2, challenge list, pk-compare advisory."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from h3_fill_idle import (  # noqa: E402
    build_fill_idle_queue,
    classify_fill_idle_shot,
    guess_take_lane,
    list_shot_takes,
    next_fill_idle_job,
    pk_compare,
)
from h3_workflow import list_h3_eligible_shots  # noqa: E402
from aifilm_grok import build_parser  # noqa: E402


def _film(tmp_path: Path) -> Path:
    root = tmp_path / "film"
    root.mkdir()
    (root / "stills").mkdir()
    (root / "takes" / "s_setup").mkdir(parents=True)
    (root / "takes" / "s_meat").mkdir(parents=True)
    meat_still = root / "stills" / "s_meat.png"
    setup_still = root / "stills" / "s_setup.png"
    meat_still.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
    setup_still.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
    # baseline grok takes (soft + meat none yet)
    setup_take = root / "takes" / "s_setup" / "grok_t1.mp4"
    setup_take.write_bytes(b"\x00" * 200_000)
    # above normal floor (≥18) so these stay P2 fill-idle, not P1 gate-fail
    (root / "takes" / "s_setup" / "grok_t1.mp4.json").write_text(
        json.dumps({"mean_absdiff": 25.0}), encoding="utf-8"
    )
    (root / "takes" / "s_soft2").mkdir(parents=True)
    soft2_still = root / "stills" / "s_soft2.png"
    soft2_still.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
    soft2 = root / "takes" / "s_soft2" / "grok_t1.mp4"
    soft2.write_bytes(b"\x00" * 200_000)
    (root / "takes" / "s_soft2" / "grok_t1.mp4.json").write_text(
        json.dumps({"mean_absdiff": 19.0}), encoding="utf-8"
    )

    spec = {
        "title": "fill-idle",
        "aspect_ratio": "9:16",
        "_i2v_profile": "hybrid_h3",
        "h3": {"enabled": True},
        "scenes": [
            {
                "id": "sc1",
                "shots": [
                    {
                        "id": "s_meat",
                        "shot_role": "hero",
                        "heat_phase": "act",
                        "wardrobe_state": "bare",
                        "dramatic_function": "action",
                        "nar": "body",
                    },
                    {
                        "id": "s_setup",
                        "shot_role": "hero",
                        "heat_phase": "setup",
                        "wardrobe_state": "clothed",
                        "dramatic_function": "setup",
                        "nar": "walk",
                    },
                    {
                        "id": "s_soft2",
                        "shot_role": "hero",
                        "heat_phase": "setup",
                        "wardrobe_state": "clothed",
                        "dramatic_function": "setup",
                        "nar": "look",
                    },
                ],
            }
        ],
    }
    (root / "film-spec.json").write_text(json.dumps(spec), encoding="utf-8")
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "stills": {
                    "s_meat": {"path": str(meat_still), "status": "approved"},
                    "s_setup": {"path": str(setup_still), "status": "approved"},
                    "s_soft2": {"path": str(soft2_still), "status": "approved"},
                }
            }
        ),
        encoding="utf-8",
    )
    return root


def test_guess_take_lane() -> None:
    assert guess_take_lane(Path("/x/takes/s1/grok_t1.mp4")) == "grok"
    assert guess_take_lane(Path("/x/takes/s1/h3_r2v.mp4")) == "h3"
    assert guess_take_lane(Path("/x/takes/s1/mystery.mp4")) == "unknown"


def test_primary_list_excludes_soft(tmp_path: Path) -> None:
    root = _film(tmp_path)
    report = list_h3_eligible_shots(root, include_challenge=False)
    ids = {r["shot_id"] for r in report["shots"]}
    assert "s_meat" in ids
    assert "s_setup" not in ids
    meat = next(r for r in report["shots"] if r["shot_id"] == "s_meat")
    assert meat["priority"] in {"P0a", "P0b", "P0c"}
    assert meat["lane"] == "primary_h3"
    assert meat["command"]


def test_challenge_includes_soft_and_orders_mean(tmp_path: Path) -> None:
    root = _film(tmp_path)
    q = build_fill_idle_queue(root, include_challenge=True)
    assert q["ok"] is True
    pending = [r for r in q["shots"] if r.get("command")]
    ids = [r["shot_id"] for r in pending]
    assert "s_meat" in ids
    # soft challenges present
    soft = [r for r in pending if r["lane"] == "challenge_grok"]
    soft_ids = {r["shot_id"] for r in soft}
    assert "s_soft2" in soft_ids and "s_setup" in soft_ids
    # P0 before P2
    meat_i = ids.index("s_meat")
    soft2_i = ids.index("s_soft2")
    assert meat_i < soft2_i
    # among P2, lower mean first (soft2=19 before setup=25)
    p2 = [r for r in pending if r["priority"] == "P2"]
    assert p2[0]["shot_id"] == "s_soft2"
    assert p2[0]["best_mean"] == 19.0


def test_next_returns_p0_first(tmp_path: Path) -> None:
    root = _film(tmp_path)
    nxt = next_fill_idle_job(root)
    assert nxt["next"]["shot_id"] == "s_meat"
    assert nxt["command"] and "s_meat" in nxt["command"]


def test_pk_compare_advisory(tmp_path: Path) -> None:
    root = _film(tmp_path)
    # add h3 take with higher mean for s_setup
    h3p = root / "takes" / "s_setup" / "h3_i2v.mp4"
    h3p.write_bytes(b"\x00" * 250_000)
    (root / "takes" / "s_setup" / "h3_i2v.mp4.json").write_text(
        json.dumps({"mean_absdiff": 30.0}), encoding="utf-8"
    )
    report = pk_compare(root, shot_id="s_setup")
    assert report["ok"] is True
    assert report["count"] == 1
    row = report["shots"][0]
    assert row["human_required"] is True
    assert row["recommended"]["mean"] == 30.0
    assert row["recommended"]["lane"] == "h3"
    assert "verify_same_face_before_promote" in row["caution"]


def test_cli_parses_challenge_next_pk() -> None:
    parser = build_parser()
    a = parser.parse_args(["h3", "list", "--root", "/tmp/x", "--challenge"])
    assert a.h3_action == "list" and a.challenge is True
    b = parser.parse_args(["h3", "next", "--root", "/tmp/x"])
    assert b.h3_action == "next"
    c = parser.parse_args(["h3", "pk-compare", "--root", "/tmp/x", "--shot-id", "s1"])
    assert c.h3_action == "pk-compare" and c.shot_id == "s1"


def test_manifest_clips_count_as_baseline(tmp_path: Path) -> None:
    """Grok often leaves path only in manifest.clips — must unlock P2."""
    root = tmp_path / "film"
    root.mkdir()
    (root / "stills").mkdir()
    still = root / "stills" / "s_only_man.png"
    still.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
    clip = root / "renders" / "s_only_man_grok.mp4"
    clip.parent.mkdir(parents=True)
    clip.write_bytes(b"\x00" * 150_000)
    (root / "film-spec.json").write_text(
        json.dumps(
            {
                "title": "man-only",
                "h3": {"enabled": True},
                "_i2v_profile": "hybrid_h3",
                "scenes": [
                    {
                        "shots": [
                            {
                                "id": "s_only_man",
                                "shot_role": "hero",
                                "heat_phase": "setup",
                                "wardrobe_state": "clothed",
                                "dramatic_function": "bridge",
                            }
                        ]
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "stills": {"s_only_man": {"path": str(still), "status": "approved"}},
                "clips": {
                    "s_only_man": {
                        "path": str(clip),
                        "mean": 22.0,
                        "provider": "grok",
                        "status": "candidate",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    takes = list_shot_takes(root, "s_only_man")
    assert len(takes) == 1
    assert takes[0]["lane"] == "grok"
    assert takes[0]["mean"] == 22.0
    q = build_fill_idle_queue(root, include_challenge=True)
    row = next(r for r in q["shots"] if r["shot_id"] == "s_only_man")
    assert row["priority"] == "P2"
    assert row["lane"] == "challenge_grok"
    assert row["command"]


def test_next_capacity_soft_offline(tmp_path: Path) -> None:
    root = _film(tmp_path)
    nxt = next_fill_idle_job(root, check_capacity=True)
    assert "capacity" in nxt
    # offline tunnel → ready is None or False; must still return meat command
    assert nxt["next"]["shot_id"] == "s_meat"
    assert nxt["command"]


def test_dual_take_second_leg_r2v(tmp_path: Path) -> None:
    """Climax primary with only I2V take should queue dual second leg R2V."""
    root = tmp_path / "film"
    root.mkdir()
    (root / "stills").mkdir()
    still = root / "stills" / "s_climax.png"
    still.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
    tdir = root / "takes" / "s_climax"
    tdir.mkdir(parents=True)
    i2v = tdir / "s_climax_h3_i2v_1.mp4"
    i2v.write_bytes(b"\x00" * 200_000)
    (tdir / "s_climax_h3_i2v_1.mp4.json").write_text(
        json.dumps({"mean_absdiff": 24.0}), encoding="utf-8"
    )
    (root / "film-spec.json").write_text(
        json.dumps(
            {
                "title": "dual",
                "h3": {"enabled": True},
                "_i2v_profile": "hybrid_h3",
                "scenes": [
                    {
                        "shots": [
                            {
                                "id": "s_climax",
                                "shot_role": "hero",
                                "heat_phase": "climax",
                                "wardrobe_state": "bare",
                                "dramatic_function": "climax",
                            }
                        ]
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (root / "manifest.json").write_text(
        json.dumps(
            {"stills": {"s_climax": {"path": str(still), "status": "approved"}}}
        ),
        encoding="utf-8",
    )
    q = build_fill_idle_queue(root, include_challenge=False)
    row = next(r for r in q["shots"] if r["shot_id"] == "s_climax")
    assert row["status"] == "pending"
    assert "dual_need_r2v" in row["reasons"]
    assert row["mode"] == "r2v"
    assert row["command"] and "--mode r2v" in row["command"]


def test_cli_pk_ledger_parses() -> None:
    parser = build_parser()
    a = parser.parse_args(
        ["h3", "pk-ledger", "--root", "/tmp/x", "--append", "--shot-id", "s1", "--winner", "/w.mp4"]
    )
    assert a.h3_action == "pk-ledger" and a.append is True


def test_classify_wait_grok_without_take(tmp_path: Path) -> None:
    root = _film(tmp_path)
    # remove soft2 takes → wait_grok_baseline
    for p in (root / "takes" / "s_soft2").rglob("*"):
        if p.is_file():
            p.unlink()
    shot = {
        "id": "s_soft2",
        "shot_role": "hero",
        "heat_phase": "setup",
        "wardrobe_state": "clothed",
    }
    from production_router import build_shot_intent

    spec = json.loads((root / "film-spec.json").read_text(encoding="utf-8"))
    intent = build_shot_intent(spec, shot)
    row = classify_fill_idle_shot(root, shot, intent=intent, has_still=True)
    assert row["status"] == "wait_grok_baseline"
    assert row["command"] is None

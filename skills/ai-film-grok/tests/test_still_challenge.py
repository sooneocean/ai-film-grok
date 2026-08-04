"""FRW i2i still-material challenge control plane."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from still_challenge import (  # noqa: E402
    build_still_challenge_queue,
    classify_still_challenge_shot,
    list_candidates,
    next_still_challenge_job,
    promote_still_challenge,
    run_still_challenge,
    still_challenge_hint_for_fill_idle,
)


def _png(path: Path, color: tuple[int, int, int] = (180, 100, 90)) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (720, 1280), color).save(path)
    return path


def _film(tmp: Path, *, shot_id: str = "s01", soft_meat: bool = True) -> Path:
    still = _png(tmp / "stills" / f"{shot_id}.png")
    shot: dict = {
        "id": shot_id,
        "shot_size": "MCU",
        "action": "embrace",
        "wardrobe_state": "bare" if soft_meat else "clothed",
        "motion_tier": "high" if soft_meat else "soft",
    }
    if soft_meat:
        shot["flags"] = ["high_motion"]
        shot["content_class"] = "act"
    spec = {
        "title": "still-challenge-test",
        "aspect_ratio": "9:16",
        "scenes": [{"id": "sc1", "shots": [shot]}],
    }
    (tmp / "film-spec.json").write_text(json.dumps(spec), encoding="utf-8")
    man = {
        "stills": {
            shot_id: {
                "path": str(still.relative_to(tmp)),
                "status": "approved",
            }
        }
    }
    (tmp / "manifest.json").write_text(json.dumps(man), encoding="utf-8")
    return tmp


def test_continue_and_poison_skip(tmp_path: Path) -> None:
    root = _film(tmp_path, shot_id="c1")
    cont = {
        "id": "c1",
        "dsl": {"chain_mode": "continue"},
        "parent_shot_id": "prev",
    }
    row = classify_still_challenge_shot(root, cont)
    assert row["priority"] == "skip"
    assert "continue" in " ".join(row["reasons"])

    poison = {"id": "c1", "tags": ["poison"], "anatomy_status": "poison"}
    row2 = classify_still_challenge_shot(root, poison)
    assert row2["status"] == "poison_blocked"


def test_s1_when_weak_take_and_soft_still(tmp_path: Path) -> None:
    root = _film(tmp_path, shot_id="m1", soft_meat=True)
    takes = root / "takes" / "m1"
    takes.mkdir(parents=True)
    (takes / "m1_grok.mp4").write_bytes(b"\x00\x00")  # placeholder existence
    motion = root / "receipts" / "motion"
    motion.mkdir(parents=True)
    (motion / "m1.json").write_text(json.dumps({"mean_absdiff": 4.0}), encoding="utf-8")
    shot = {
        "id": "m1",
        "motion_tier": "high",
        "flags": ["high_motion"],
        "wardrobe_state": "bare",
    }
    row = classify_still_challenge_shot(
        root,
        shot,
        intent={"motion_tier": "high", "content_class": "act"},
    )
    assert row["priority"] == "S1"
    assert row["status"] == "pending"
    assert row["command"] and "still-challenge run" in row["command"]


def test_queue_and_next_include_rate(tmp_path: Path) -> None:
    root = _film(tmp_path, shot_id="q1")
    takes = root / "takes" / "q1"
    takes.mkdir(parents=True)
    (takes / "q1.mp4").write_bytes(b"x")
    motion = root / "receipts" / "motion"
    motion.mkdir(parents=True)
    (motion / "q1.json").write_text(json.dumps({"mean_absdiff": 3.0}), encoding="utf-8")
    q = build_still_challenge_queue(root)
    assert q["ok"] is True
    assert "rate" in q
    assert q["image_min_interval_s"] == 30.0
    nxt = next_still_challenge_job(root)
    assert nxt["max_submits_default"] == 1
    assert "image_wait_s" in nxt


def test_run_dry_and_execute_mock(tmp_path: Path) -> None:
    root = _film(tmp_path, shot_id="r1")
    dry = run_still_challenge(root, "r1", execute=False)
    assert dry["status"] == "dry_run"
    assert dry["execute"] is False

    cand_src = _png(tmp_path / "mock_out.png", (50, 120, 200))

    def runner(args: list[str]) -> dict:
        if args[0] == "upload":
            return {"data": {"url": "https://cdn.example.com/src.png"}}
        if args[0] == "img2image":
            return {
                "data": {"image_url": "https://cdn.example.com/out.png"},
                "local_path": str(cand_src),
            }
        raise AssertionError(args)

    # Patch download to use local_path path in our run — we already handle local_path
    report = run_still_challenge(
        root,
        "r1",
        execute=True,
        frw_runner=runner,
        skip_capability_gate=True,
        seed=42,
    )
    assert report["ok"] is True
    assert report["status"] == "candidate"
    assert Path(report["candidate_path"]).is_file()
    assert list_candidates(root, "r1")


def test_promote_archives_and_updates_manifest(tmp_path: Path) -> None:
    root = _film(tmp_path, shot_id="p1")
    old = root / "stills" / "p1.png"
    old_sha = old.read_bytes()
    cand = _png(root / "takes" / "p1" / "still_frw_1.png", (10, 20, 30))
    rep = promote_still_challenge(
        root,
        "p1",
        source=cand,
        identity_approved=True,
        anatomy_safe=True,
        review_note="frw-i2i id-ok",
    )
    assert rep["ok"] is True
    assert Path(rep["still_path"]).is_file()
    assert Path(rep["still_path"]).read_bytes() != old_sha
    assert rep["archived_previous"]
    man = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    assert man["stills"]["p1"]["provider"] == "frw_i2i"


def test_fill_idle_hint() -> None:
    # unit-only: hint returns None without film; with weak row needs root
    assert still_challenge_hint_for_fill_idle("/tmp/nope", None) is None

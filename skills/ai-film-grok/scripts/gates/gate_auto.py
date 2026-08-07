#!/usr/bin/env python3
"""Automated machine-verifiable gate ladder (2026-08-04 · opt 2.39.11).

Runs everything that can be proven without a human eyeball:
  means → i2v-final-gate write → five_track ensure + sex_sfx inject
  → true_video scan → variety → cinematic-gate

Does **not** replace:
  pilot user approval · multi-take human PK · review-final scorecard

Optimizations:
  · fast_path when gate-auto + i2v-final + cinematic already green (unless force)
  · i2v hard only when there are motion rows / approved clips to grade

Class analogy: airport auto-checklist for instruments; pilot still boards.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from util import read_json, utc_now, write_json
from util.errors import FilmError

RECEIPT = "gate-auto.json"
I2V_RECEIPT = "i2v-final-gate.json"
CIN_RECEIPT = "cinematic-gate.json"

# Still requires a human (never auto-green these as "DONE")
HUMAN_ONLY = (
    "pilot_user_approval",
    "multi_take_pk_promote",
    "review_final_scorecard",
    "paid_budget_ack",
)


class GateAutoError(FilmError):
    pass


def skip_enabled() -> bool:
    return os.environ.get("AIFILM_SKIP_GATE_AUTO", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def machine_receipts_green(root: Path | str) -> dict[str, Any]:
    """True when machine ladder receipts are already ok (no re-measure needed)."""
    base = Path(root).expanduser().resolve()
    auto = read_json(base / "receipts" / RECEIPT) or {}
    i2v = read_json(base / "receipts" / I2V_RECEIPT) or {}
    cin = read_json(base / "receipts" / CIN_RECEIPT) or {}
    ready = read_json(base / "receipts" / "machine-ready.json") or {}
    auto_ok = isinstance(auto, dict) and auto.get("ok") is True and not auto.get("skipped")
    i2v_ok = isinstance(i2v, dict) and i2v.get("ok") is True
    cin_ok = isinstance(cin, dict) and cin.get("ok") is True
    ready_ok = isinstance(ready, dict) and ready.get("ok") is True
    green = bool(ready_ok or (auto_ok and i2v_ok and cin_ok))
    return {
        "ok": green,
        "gate_auto": auto_ok,
        "i2v_final": i2v_ok,
        "cinematic": cin_ok,
        "machine_ready": ready_ok,
        "human_pending": list(auto.get("human_pending") or []) if isinstance(auto, dict) else [],
    }


def ensure_machine_lane(
    root: Path | str,
    *,
    force: bool = False,
    write: bool = True,
    fix_sex_sfx: bool = True,
    measure_i2v: bool = True,
    promote_single: bool = True,
    run_variety: bool = True,
    run_cinematic: bool = True,
) -> dict[str, Any]:
    """Single machine-lane entry for ship-prep / closeout / export / advance.

    Returns green fast when receipts already ok; otherwise runs full gate-auto once.
    """
    base = Path(root).expanduser().resolve()
    if not force:
        st = machine_receipts_green(base)
        if st.get("ok"):
            return {
                "ok": True,
                "fast_path": True,
                "ensured": True,
                "root": str(base),
                "blocked_by": None,
                "human_pending": st.get("human_pending") or [],
                "steps": [{"id": "cinematic_gate", "ok": True, "detail": "pre-green"}],
                "note": "ensure_machine_lane: already green",
            }
    return run_gate_auto(
        base,
        write=write,
        force=force,
        fix_sex_sfx=fix_sex_sfx,
        measure_i2v=measure_i2v,
        promote_single=promote_single,
        run_variety=run_variety,
        run_cinematic=run_cinematic,
    )


def next_machine_lane_action(
    root: Path | str,
    *,
    prefer_ship_prep: bool = False,
) -> dict[str, str] | None:
    """One next action for post-clips machine path, or None if already green.

    Prefer gate-auto (single ladder). ship-prep only when prefer_ship_prep and
    multi-take shortlist not done (shortlist/pk package).
    """
    base = Path(root).expanduser().resolve()
    r = str(base)
    if machine_receipts_green(base).get("ok"):
        return None
    if prefer_ship_prep:
        ship = read_json(base / "receipts" / "ship-prep.json") or {}
        sel = read_json(base / "receipts" / "select-shortlist.json") or {}
        takes_dir = base / "takes"
        has_takes = takes_dir.is_dir() and any(takes_dir.rglob("*.mp4"))
        multi_pending = has_takes and not (isinstance(sel, dict) and sel.get("shots"))
        human_pk = bool(isinstance(ship, dict) and ship.get("human_pk_required"))
        if (multi_pending or human_pk) and ship.get("ok") is not True:
            why = "多 take / 人审 PK — ship-prep（shortlist+pk-dailies 一页）再 gate-auto"
            if isinstance(ship, dict) and ship.get("human_one_pager"):
                why = f"{why} · 见 {ship.get('human_one_pager')}"
            return {
                "id": "ship-prep",
                "cmd": f'aifilm ship-prep --root "{r}"',
                "why": why,
            }
        if human_pk and ship.get("ok") is True:
            pager = (
                ship.get("human_one_pager")
                or ship.get("dailies_path")
                or "receipts/pk-dailies.md"
            )
            return {
                "id": "gate-auto",
                "cmd": f'aifilm gate-auto --root "{r}"',
                "why": (
                    f"机读过闸；人审 PK 仍待 promote（{pager}）—"
                    "gate 可先跑，export 前再 promote"
                ),
            }
    return {
        "id": "gate-auto",
        "cmd": f'aifilm gate-auto --root "{r}"',
        "why": "机读过闸：mean/i2v/sex_sfx/cinematic（无需手点）",
    }


def _has_approved_clips(root: Path) -> bool:
    man = read_json(root / "manifest.json") or {}
    clips = man.get("clips") if isinstance(man.get("clips"), dict) else {}
    for rec in clips.values():
        if isinstance(rec, dict) and str(rec.get("status") or "") == "approved":
            return True
    return False


def _step(
    sid: str,
    *,
    ok: bool,
    detail: str = "",
    hard: bool = True,
    next_cmd: str | None = None,
    codes: list[str] | None = None,
    human: bool = False,
) -> dict[str, Any]:
    return {
        "id": sid,
        "ok": ok,
        "hard": hard,
        "human": human,
        "detail": detail,
        "next_cmd": next_cmd,
        "codes": codes or [],
    }


def _load_spec(root: Path) -> dict[str, Any]:
    return read_json(root / "film-spec.json") or {}


def _write_spec(root: Path, spec: dict[str, Any]) -> None:
    write_json(root / "film-spec.json", spec)


def auto_inject_sex_sfx(root: Path) -> dict[str, Any]:
    """Machine-fill missing meat sex_sfx events (write-spec already knows how)."""
    spec = _load_spec(root)
    if not isinstance(spec, dict) or not spec:
        return {"ok": True, "skipped": True, "reason": "no_spec"}
    heat = str(spec.get("heat_scale") or "").strip().lower()
    shots: list[dict[str, Any]] = []
    for scene in spec.get("scenes") or []:
        if not isinstance(scene, dict):
            continue
        for sh in scene.get("shots") or []:
            if isinstance(sh, dict):
                shots.append(sh)
    if not shots:
        return {"ok": True, "skipped": True, "reason": "no_shots"}
    try:
        from sound_plan import inject_sex_sfx_from_shots

        sp = spec.get("sound_plan") if isinstance(spec.get("sound_plan"), dict) else {}
        before = len(sp.get("events") or []) if isinstance(sp.get("events"), list) else 0
        sp2 = inject_sex_sfx_from_shots(sp or {"events": []}, shots, heat_scale=heat)
        if isinstance(sp2, dict):
            spec["sound_plan"] = sp2
            after = len(sp2.get("events") or [])
            _write_spec(root, spec)
            return {
                "ok": True,
                "injected": max(0, after - before),
                "events_after": after,
            }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)[:200]}
    return {"ok": True, "injected": 0}


def auto_i2v_motion_gate(root: Path, *, write: bool = True) -> dict[str, Any]:
    """Measure means + write i2v-high-motion-audit + i2v-final-gate."""
    try:
        from cli_motion import i2v_motion_gate_from_rows
        from i2v_motion_gate import ensure_take_means

        mm = ensure_take_means(root, recompute=False, write_sidecars=True)
        rep = i2v_motion_gate_from_rows(
            [],
            root=root,
            write_receipts=write,
            auto_from_root=True,
            raw_complete=True,
            kb_fallback=False,
            style_ok=True,
        )
        return {
            "ok": bool(rep.get("ok")),
            "row_count": rep.get("row_count"),
            "means": {
                "measured": mm.get("measured_count"),
                "skipped": mm.get("skipped_count"),
                "errors": mm.get("error_count"),
            },
            "gate": (rep.get("gate") or {}).get("ok"),
            "receipts": rep.get("receipts"),
            "codes": list((rep.get("gate") or {}).get("codes") or []),
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)[:240]}


def auto_promote_single_takes(root: Path) -> dict[str, Any]:
    """When a shot has exactly one take, promote it without human PK.

    A1 · shortlist ok=false (e.g. multi-seed without anti-hijack) must not report
    promote step as green.
    """
    try:
        from workflow_pack import select_shortlist

        # promote only when shortlist has single-take rows; multi still deferred
        rep = select_shortlist(root, promote=True, measure_missing=True)
        multi = 0
        for s in rep.get("shots") or []:
            if isinstance(s, dict) and int(s.get("take_count") or 0) >= 2:
                multi += 1
        shortlist_ok = bool(rep.get("ok", True))
        promote_blocked = bool(rep.get("promote_blocked"))
        return {
            "ok": shortlist_ok and not promote_blocked,
            "promoted": len(rep.get("promoted") or []),
            "multi_take_shots": multi,
            "human_pk_still_required": multi > 0,
            "promote_blocked": promote_blocked,
            "codes": list(rep.get("codes") or []),
            "detail": (
                f"shortlist ok={shortlist_ok} blocked={promote_blocked} "
                f"codes={rep.get('codes') or []}"
                if not shortlist_ok or promote_blocked
                else "single-take auto-promoted; multi-take needs human PK"
            ),
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)[:200]}


def run_gate_auto(
    root: Path | str,
    *,
    write: bool = True,
    fix_sex_sfx: bool = True,
    measure_i2v: bool = True,
    promote_single: bool = True,
    run_variety: bool = True,
    run_cinematic: bool = True,
    force: bool = False,
) -> dict[str, Any]:
    """Full machine ladder. Returns red/green with human_only remaining list.

    ``force=False`` (default): if gate-auto + i2v-final + cinematic already green,
    return a fast_path receipt without re-measuring means (export/closeout thrash).
    """
    base = Path(root).expanduser().resolve()
    if skip_enabled():
        out = {
            "schema_version": 1,
            "kind": "gate-auto",
            "ok": True,
            "skipped": True,
            "escape": "AIFILM_SKIP_GATE_AUTO=1",
            "at": utc_now(),
            "root": str(base),
        }
        if write:
            write_json(base / "receipts" / RECEIPT, out)
        return out

    if not force:
        status = machine_receipts_green(base)
        if status.get("ok"):
            prev = read_json(base / "receipts" / RECEIPT) or {}
            # No rewrite when already green+fast — saves I/O and state-hash churn
            if (
                isinstance(prev, dict)
                and prev.get("ok") is True
                and prev.get("fast_path") is True
                and write
            ):
                return {
                    **prev,
                    "fast_path": True,
                    "machine_verified": True,
                    "root": str(base),
                    "note": "fast_path_reuse: green receipts unchanged",
                }
            out = {
                **(prev if isinstance(prev, dict) else {}),
                "schema_version": 1,
                "kind": "gate-auto",
                "ok": True,
                "fast_path": True,
                "at": utc_now(),
                "root": str(base),
                "machine_verified": True,
                "human_pending": status.get("human_pending") or [],
                "human_only_forever": list(HUMAN_ONLY),
                "note": "fast_path: machine receipts already green (pass force=True to re-measure)",
            }
            if write:
                write_json(base / "receipts" / RECEIPT, out)
                ready_path = base / "receipts" / "machine-ready.json"
                if not ready_path.is_file():
                    write_json(
                        ready_path,
                        {
                            "schema_version": 1,
                            "kind": "machine-ready",
                            "ok": True,
                            "at": out["at"],
                            "gate_auto": True,
                        },
                    )
            return out

    steps: list[dict[str, Any]] = []
    r = str(base)
    (base / "receipts").mkdir(parents=True, exist_ok=True)

    # 1) five_track defaults + sex_sfx auto inject
    try:
        from five_track import ensure_five_track_defaults, plan_five_track

        spec = _load_spec(base)
        if isinstance(spec, dict) and spec:
            ensure_five_track_defaults(spec)
            if write:
                _write_spec(base, spec)
        if fix_sex_sfx:
            sfx = auto_inject_sex_sfx(base)
            steps.append(
                _step(
                    "sex_sfx_inject",
                    ok=bool(sfx.get("ok")),
                    detail=str(sfx)[:180],
                    hard=False,
                )
            )
        ft = plan_five_track(base, write=write)
        steps.append(
            _step(
                "five_track",
                ok=bool(ft.get("ok") or not ft.get("enabled")),
                detail=(
                    f"enabled={ft.get('enabled')} "
                    f"sex={ft.get('sex_sfx', {}).get('covered')}/"
                    f"{ft.get('sex_sfx', {}).get('required')}"
                ),
                hard=bool(ft.get("enabled")),
                next_cmd=ft.get("next_cmd"),
                codes=list(ft.get("codes") or []),
            )
        )
    except Exception as exc:  # noqa: BLE001
        steps.append(_step("five_track", ok=False, detail=str(exc)[:200]))

    # 2) single-take promote (no human for 1 take)
    if promote_single:
        pr = auto_promote_single_takes(base)
        steps.append(
            _step(
                "promote_single",
                ok=bool(pr.get("ok")),
                hard=False,
                detail=pr.get("detail") or str(pr)[:160],
                human=bool(pr.get("human_pk_still_required")),
            )
        )
        if pr.get("human_pk_still_required"):
            steps.append(
                _step(
                    "multi_take_pk",
                    ok=False,
                    hard=False,
                    human=True,
                    detail=f"multi_take_shots={pr.get('multi_take_shots')} — human PK",
                    next_cmd=f'aifilm h3 pk-compare --root "{r}"; aifilm select-shortlist --root "{r}" --promote',
                )
            )

    # 3) i2v motion gate auto measure+write
    if measure_i2v:
        mg = auto_i2v_motion_gate(base, write=write)
        rows = int(mg.get("row_count") or 0)
        has_clips = _has_approved_clips(base)
        # Soft when nothing to grade (empty pilot / pre-media root)
        if rows == 0 and not has_clips:
            i2v_ok = True
            i2v_hard = False
            i2v_detail = "no approved clips / zero rows — i2v gate soft skip"
        else:
            i2v_ok = bool(mg.get("ok"))
            i2v_hard = True
            i2v_detail = f"rows={rows} means={mg.get('means')} gate={mg.get('gate')}" + (
                f" err={mg.get('error')}" if mg.get("error") else ""
            )
        steps.append(
            _step(
                "i2v_motion",
                ok=i2v_ok,
                detail=i2v_detail,
                hard=i2v_hard,
                next_cmd=(
                    None
                    if i2v_ok
                    else f'aifilm i2v-motion-gate --root "{r}" --write  # fix weak means'
                ),
                codes=list(mg.get("codes") or []),
            )
        )

    # 4) true video
    try:
        from true_video_policy import scan_manifest_true_video

        tv = scan_manifest_true_video(base)
        steps.append(
            _step(
                "true_video",
                ok=bool(tv.get("ok") or tv.get("skipped")),
                detail=f"checked={tv.get('checked')} viol={len(tv.get('violations') or [])}",
                hard=True,
                next_cmd=(
                    None
                    if tv.get("ok") or tv.get("skipped")
                    else "re-I2V; ban Ken Burns approved clips"
                ),
                codes=list(tv.get("codes") or []),
            )
        )
    except Exception as exc:  # noqa: BLE001
        steps.append(_step("true_video", ok=False, detail=str(exc)[:200]))

    # 5) variety (machine lint of film-spec) + I1.2 variety_pixel
    if run_variety:
        try:
            from workflow_pack import variety_pixel_bind, variety_precheck

            var = variety_precheck(base, write=write)
            meat_n = int(var.get("meat_shot_count") or 0)
            # If no meat shots, variety often "ok" with empty matrix — fine
            steps.append(
                _step(
                    "variety",
                    ok=bool(var.get("ok")),
                    detail=f"issues={len(var.get('issues') or [])} meat={meat_n}",
                    hard=bool(meat_n >= 2),
                    next_cmd=(
                        None
                        if var.get("ok")
                        else f'aifilm variety-precheck --root "{r}"  # fix film-spec'
                    ),
                    codes=[
                        str(i.get("code")) for i in (var.get("issues") or []) if isinstance(i, dict)
                    ],
                )
            )
            vpx = variety_pixel_bind(base, write=write)
            steps.append(
                _step(
                    "variety_pixel",
                    ok=bool(vpx.get("ok") or vpx.get("skipped")),
                    detail=(
                        "skipped"
                        if vpx.get("skipped")
                        else f"issues={len(vpx.get('issues') or [])}"
                    ),
                    hard=bool(meat_n >= 2) and not bool(vpx.get("skipped")),
                    next_cmd=vpx.get("next_cmd"),
                    codes=[
                        str(i.get("code"))
                        for i in (vpx.get("issues") or [])
                        if isinstance(i, dict)
                    ],
                )
            )
        except Exception as exc:  # noqa: BLE001 — A1: never silent-green variety
            steps.append(
                _step(
                    "variety",
                    ok=False,
                    hard=True,
                    detail=f"variety probe failed: {exc}"[:200],
                    next_cmd=f'aifilm variety-precheck --root "{r}"',
                )
            )

    # 6) cinematic composite (uses fresh i2v receipts)
    if run_cinematic:
        try:
            from cinematic_gate import run_cinematic_gate

            cin = run_cinematic_gate(
                base,
                write=write,
                run_ship_prep=False,
                skip_variety=True,  # already did
                skip_five_track=True,
                auto_i2v=False,  # already measured
            )
            steps.append(
                _step(
                    "cinematic_gate",
                    ok=bool(cin.get("ok")),
                    detail=f"blocked_by={cin.get('blocked_by')}",
                    hard=True,
                    next_cmd=cin.get("next_cmd"),
                )
            )
        except TypeError:
            # older signature without auto_i2v
            from cinematic_gate import run_cinematic_gate

            cin = run_cinematic_gate(
                base,
                write=write,
                run_ship_prep=False,
                skip_variety=True,
                skip_five_track=True,
            )
            steps.append(
                _step(
                    "cinematic_gate",
                    ok=bool(cin.get("ok")),
                    detail=f"blocked_by={cin.get('blocked_by')}",
                    hard=True,
                    next_cmd=cin.get("next_cmd"),
                )
            )
        except Exception as exc:  # noqa: BLE001
            steps.append(_step("cinematic_gate", ok=False, detail=str(exc)[:200]))

    hard_failed = [s for s in steps if not s.get("ok") and s.get("hard") and not s.get("human")]
    human_pending = [s for s in steps if s.get("human") and not s.get("ok")]
    ok = not hard_failed
    blocked = hard_failed[0] if hard_failed else None

    out = {
        "schema_version": 1,
        "kind": "gate-auto",
        "at": utc_now(),
        "root": str(base),
        "ok": ok,
        "steps": steps,
        "blocked_by": (blocked or {}).get("id"),
        "hard_failed": [s["id"] for s in hard_failed],
        "human_pending": [s["id"] for s in human_pending],
        "human_only_forever": list(HUMAN_ONLY),
        "next_cmd": (blocked or {}).get("next_cmd")
        or (
            f'aifilm final --root "{r}" --post-engine hyperframes --music-mood rnb --tts-backend edge'
            if ok and not human_pending
            else (human_pending[0].get("next_cmd") if human_pending else None)
        ),
        "machine_verified": ok,
        "fast_path": False,
        "force": bool(force),
        "note": (
            "Machine ladder only. Still needs human for pilot / multi-take PK / "
            "review-final. Does not fake motion floors."
        ),
    }
    if write:
        write_json(base / "receipts" / RECEIPT, out)
        # Compact pointer for dispatch/next_actions (avoid re-reading three files)
        write_json(
            base / "receipts" / "machine-ready.json",
            {
                "schema_version": 1,
                "kind": "machine-ready",
                "ok": ok,
                "at": out["at"],
                "blocked_by": out.get("blocked_by"),
                "human_pending": out.get("human_pending"),
                "gate_auto": ok,
            },
        )
    return out

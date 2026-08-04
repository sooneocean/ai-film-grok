#!/usr/bin/env python3
"""Composite cinematic delivery gate (Wave ε · 2026-08-04).

One-shot red/green before final/export-desktop:

  true_video · i2v_final · variety · five_track · edit_rhythm · inventory

Class analogy: pre-flight checklist for a cinema flight — all lights green or no takeoff.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from util import read_json, utc_now, write_json

RECEIPT_NAME = "cinematic-gate.json"


class CinematicGateError(RuntimeError):
    """Desktop/export blocked by cinematic-gate."""


def skip_enabled() -> bool:
    return os.environ.get("AIFILM_SKIP_CINEMATIC_GATE", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _step(
    sid: str,
    *,
    ok: bool,
    hard: bool = True,
    detail: str = "",
    next_cmd: str | None = None,
    codes: list[str] | None = None,
    skipped: bool = False,
) -> dict[str, Any]:
    return {
        "id": sid,
        "ok": ok,
        "hard": hard,
        "detail": detail,
        "next_cmd": next_cmd,
        "codes": codes or [],
        "skipped": skipped,
    }


def run_cinematic_gate(
    root: Path | str,
    *,
    write: bool = True,
    run_ship_prep: bool = False,
    skip_variety: bool = False,
    skip_five_track: bool = False,
    auto_i2v: bool = True,
) -> dict[str, Any]:
    """Evaluate composite cinema readiness. Returns receipt-shaped report.

    ``auto_i2v`` (default True): when i2v-final-gate missing/red, machine-measure
    means and rewrite the gate receipt so agents need not hand-run the step.
    """
    base = Path(root).expanduser().resolve()
    if skip_enabled():
        rep = {
            "schema_version": 1,
            "kind": "cinematic-gate",
            "ok": True,
            "skipped": True,
            "escape": "AIFILM_SKIP_CINEMATIC_GATE=1",
            "at": utc_now(),
            "root": str(base),
            "steps": [],
            "desktop_export_allowed": True,
        }
        if write:
            _write_receipt(base, rep)
        return rep

    steps: list[dict[str, Any]] = []
    r = str(base)

    # 0) optional ship-prep ladder first
    if run_ship_prep:
        try:
            from workflow_pack import ship_prep

            sp = ship_prep(base, write=write)
            steps.append(
                _step(
                    "ship_prep",
                    ok=bool(sp.get("ok")),
                    hard=True,
                    detail=f"blocked_by={sp.get('blocked_by')}",
                    next_cmd=sp.get("next_cmd"),
                )
            )
        except Exception as exc:  # noqa: BLE001
            steps.append(
                _step(
                    "ship_prep",
                    ok=False,
                    detail=str(exc)[:200],
                    next_cmd=f'aifilm ship-prep --root "{r}"',
                )
            )

    # 1) true-video-only hero clips
    try:
        from true_video_policy import scan_manifest_true_video

        tv = scan_manifest_true_video(base)
        steps.append(
            _step(
                "true_video",
                ok=bool(tv.get("ok") or tv.get("skipped")),
                hard=True,
                detail=(
                    "skipped"
                    if tv.get("skipped")
                    else f"checked={tv.get('checked')} viol={len(tv.get('violations') or [])}"
                ),
                next_cmd=(
                    None
                    if tv.get("ok") or tv.get("skipped")
                    else "re-I2V Grok/H3; remove Ken Burns/still-motion approved clips"
                ),
                codes=list(tv.get("codes") or []),
            )
        )
    except Exception as exc:  # noqa: BLE001
        steps.append(_step("true_video", ok=False, detail=str(exc)[:200]))

    # 2) inventory / clips_complete
    try:
        from film_spec import validate_film_spec
        from shot_inventory import check_shot_inventory

        man = read_json(base / "manifest.json") or {}
        clips = man.get("clips") if isinstance(man.get("clips"), dict) else {}
        approved = [
            sid
            for sid, rec in clips.items()
            if isinstance(rec, dict) and rec.get("status") == "approved"
        ]
        spec = read_json(base / "film-spec.json") or {}
        shot_ids: list[str] = []
        if isinstance(spec, dict) and spec:
            try:
                shot_ids = [
                    str(s["id"]) for s in validate_film_spec(spec, assign_missing_ids=False)
                ]
            except Exception:
                for scene in spec.get("scenes") or []:
                    if not isinstance(scene, dict):
                        continue
                    for sh in scene.get("shots") or []:
                        if isinstance(sh, dict) and sh.get("id"):
                            shot_ids.append(str(sh["id"]))
        gates = man.get("gates") if isinstance(man.get("gates"), dict) else {}
        if not shot_ids:
            # Empty spec: not a clip-inventory failure (ship-prep / early export fixtures)
            steps.append(
                _step(
                    "inventory",
                    ok=True,
                    hard=False,
                    skipped=True,
                    detail="no_shots_in_spec",
                )
            )
        else:
            inv = check_shot_inventory(shot_ids, approved)
            clips_ok = bool(gates.get("clips_complete")) or bool(inv.get("complete"))
            steps.append(
                _step(
                    "inventory",
                    ok=clips_ok or bool(inv.get("ok")),
                    hard=True,
                    detail=(
                        f"shots={inv.get('shot_count')} approved={inv.get('approved_clip_count')} "
                        f"missing={inv.get('missing_clips')}"
                    ),
                    next_cmd=(
                        None
                        if clips_ok or inv.get("ok")
                        else f'aifilm register-clip --root "{r}" …'
                    ),
                    codes=list(inv.get("codes") or []),
                )
            )
    except Exception as exc:  # noqa: BLE001
        steps.append(_step("inventory", ok=False, detail=str(exc)[:200]))

    # 3) i2v final gate receipt (auto-measure when missing/red)
    gate_path = base / "receipts" / "i2v-final-gate.json"
    gate = read_json(gate_path) if gate_path.is_file() else None
    if isinstance(gate, dict) and gate.get("ok") is True:
        steps.append(
            _step(
                "i2v_final",
                ok=True,
                detail="receipts/i2v-final-gate.json ok=true",
            )
        )
    else:
        auto_ok = False
        detail = "missing or ok!=true"
        codes: list[str] = ["I2V_FINAL_GATE_NOT_OK"]
        try:
            from i2v_motion_gate import i2v_motion_gate_skip_enabled

            if i2v_motion_gate_skip_enabled():
                auto_ok = True
                detail = "AIFILM_SKIP_I2V_MOTION_GATE"
                codes = []
            elif auto_i2v and write:
                from cli_motion import i2v_motion_gate_from_rows
                from i2v_motion_gate import ensure_take_means

                ensure_take_means(base, recompute=False, write_sidecars=True)
                mg = i2v_motion_gate_from_rows(
                    [],
                    root=base,
                    write_receipts=True,
                    auto_from_root=True,
                )
                auto_ok = bool(mg.get("ok"))
                detail = f"auto-wrote gate ok={auto_ok} rows={mg.get('row_count')}"
                codes = list((mg.get("gate") or {}).get("codes") or []) or (
                    [] if auto_ok else ["I2V_FINAL_GATE_NOT_OK"]
                )
            else:
                detail = (
                    "missing receipt"
                    if not gate_path.is_file()
                    else f"ok={None if not isinstance(gate, dict) else gate.get('ok')}"
                )
        except Exception as exc:
            detail = f"auto_i2v failed: {exc}"[:200]
        steps.append(
            _step(
                "i2v_final",
                ok=auto_ok,
                hard=True,
                detail=detail,
                next_cmd=(
                    None
                    if auto_ok
                    else f'aifilm i2v-motion-gate --root "{r}" --write  # or gate-auto'
                ),
                codes=codes,
            )
        )

    # 4) variety (hard when meat present)
    if skip_variety or os.environ.get("AIFILM_SKIP_VARIETY_PREFLIGHT", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        steps.append(_step("variety", ok=True, hard=False, skipped=True, detail="skipped"))
    else:
        try:
            from workflow_pack import variety_precheck

            var = variety_precheck(base, write=write)
            steps.append(
                _step(
                    "variety",
                    ok=bool(var.get("ok")),
                    hard=True,
                    detail=f"issues={len(var.get('issues') or [])}",
                    next_cmd=(None if var.get("ok") else f'aifilm variety-precheck --root "{r}"'),
                    codes=[
                        str(i.get("code")) for i in (var.get("issues") or []) if isinstance(i, dict)
                    ],
                )
            )
        except Exception as exc:  # noqa: BLE001
            steps.append(
                _step(
                    "variety",
                    ok=True,
                    hard=False,
                    detail=f"advisory skip: {exc}"[:160],
                    skipped=True,
                )
            )

    # 5) five-track
    if skip_five_track:
        steps.append(_step("five_track", ok=True, hard=False, skipped=True))
    else:
        try:
            from five_track import plan_five_track

            ft = plan_five_track(base, write=write)
            enabled = bool(ft.get("enabled"))
            ok = bool(ft.get("ok") or not enabled)
            steps.append(
                _step(
                    "five_track",
                    ok=ok,
                    hard=enabled,
                    detail=(
                        f"enabled={enabled} sex={ft.get('sex_sfx', {}).get('covered')}/"
                        f"{ft.get('sex_sfx', {}).get('required')}"
                    ),
                    next_cmd=ft.get("next_cmd") if not ok else None,
                    codes=list(ft.get("codes") or []),
                )
            )
        except Exception as exc:  # noqa: BLE001
            steps.append(
                _step(
                    "five_track",
                    ok=True,
                    hard=False,
                    detail=f"skip: {exc}"[:160],
                    skipped=True,
                )
            )

    # 6) edit rhythm / visual_fit advisory
    try:
        from edit_policy import default_visual_fit, lint_equal_duration_ppt

        spec = read_json(base / "film-spec.json") or {}
        if isinstance(spec, dict):
            fit = str(spec.get("visual_fit") or default_visual_fit(spec) or "slot")
        else:
            fit = "slot"
        shots: list[dict[str, Any]] = []
        if isinstance(spec, dict):
            for scene in spec.get("scenes") or []:
                if not isinstance(scene, dict):
                    continue
                for sh in scene.get("shots") or []:
                    if isinstance(sh, dict):
                        shots.append(sh)
        ppt = lint_equal_duration_ppt(shots, visual_fit=fit)
        steps.append(
            _step(
                "edit_rhythm",
                ok=bool(ppt.get("ok")),
                hard=False,
                detail=f"visual_fit={fit} ppt_ok={ppt.get('ok')}",
                next_cmd=(None if ppt.get("ok") else "set visual_fit=vo or vary duration_sec"),
                codes=list(ppt.get("codes") or []),
            )
        )
    except Exception as exc:  # noqa: BLE001
        steps.append(_step("edit_rhythm", ok=True, hard=False, detail=str(exc)[:120], skipped=True))

    # 7) film_core advisory receipt if present
    fc = read_json(base / "receipts" / "film-core-closeout.json") or {}
    if isinstance(fc, dict) and fc:
        steps.append(
            _step(
                "film_core",
                ok=bool(fc.get("ok")),
                hard=False,
                detail=f"ok={fc.get('ok')}",
                next_cmd=f'aifilm closeout status --root "{r}"' if not fc.get("ok") else None,
            )
        )

    hard_failed = [s for s in steps if not s.get("ok") and s.get("hard") and not s.get("skipped")]
    soft_failed = [
        s for s in steps if not s.get("ok") and not s.get("hard") and not s.get("skipped")
    ]
    ok = not hard_failed
    blocked = hard_failed[0] if hard_failed else None
    next_cmd = (blocked or {}).get("next_cmd")
    if ok and not next_cmd:
        next_cmd = f'aifilm final --root "{r}" --post-engine hyperframes --music-mood rnb --tts-backend edge'

    report = {
        "schema_version": 1,
        "kind": "cinematic-gate",
        "at": utc_now(),
        "root": str(base),
        "ok": ok,
        "steps": steps,
        "blocked_by": (blocked or {}).get("id"),
        "soft_issues": [s["id"] for s in soft_failed],
        "next_cmd": next_cmd,
        "desktop_export_allowed": ok,
        "note": (
            "true_video→inventory→i2v_final→variety→five_track→edit_rhythm; "
            "ok=true required for honest desktop export (plus post-audit)"
        ),
    }
    if write:
        _write_receipt(base, report)
    return report


def _write_receipt(root: Path, report: dict[str, Any]) -> Path:
    rec = root / "receipts"
    rec.mkdir(parents=True, exist_ok=True)
    path = rec / RECEIPT_NAME
    write_json(path, report)
    return path


def assert_cinematic_gate_for_export(root: Path | str) -> dict[str, Any]:
    """Hard block export-desktop when cinematic-gate not ok (missing = fail).

    Before fail: run gate-auto once (measure means / inject / rewrite receipts),
    then refresh cinematic-gate — agents need not hand-click the ladder.
    """
    base = Path(root).expanduser().resolve()
    if skip_enabled():
        return {"ok": True, "skipped": True, "escape": "AIFILM_SKIP_CINEMATIC_GATE=1"}
    path = base / "receipts" / RECEIPT_NAME
    report = read_json(path) if path.is_file() else None
    if isinstance(report, dict) and report.get("ok") is True:
        return {"ok": True, "gate": report, "path": str(path)}

    # Deep auto: full machine ladder then re-read cinematic
    try:
        from gate_auto import run_gate_auto

        run_gate_auto(base, write=True)
    except Exception:
        pass
    report = run_cinematic_gate(base, write=True, auto_i2v=True)
    if not isinstance(report, dict) or report.get("ok") is not True:
        raise CinematicGateError(
            "Desktop export blocked by cinematic-gate (ok!=true); "
            f'run: aifilm gate-auto --root "{base}". '
            f"blocked_by={report.get('blocked_by') if isinstance(report, dict) else None}. "
            "Escape: AIFILM_SKIP_CINEMATIC_GATE=1"
        )
    return {"ok": True, "gate": report, "path": str(path)}

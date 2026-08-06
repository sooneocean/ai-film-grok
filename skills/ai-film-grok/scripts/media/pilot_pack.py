"""Pilot GO pack — one-screen evidence before bulk.

Wave A2 · workflow optimize: undress/union/rhythm coverage + media + scorecard
+ approval + heat + state-index gaps → receipts/pilot-go.json.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from util import read_json, utc_now, write_json

RECEIPT_REL = Path("receipts/pilot-go.json")
MEAT_BEATS = frozenset(
    {"undress", "union", "rhythm", "entry", "lock", "finish", "foreplay", "act", "climax"}
)


def _root(path: Path | str) -> Path:
    return Path(path).expanduser().resolve()


def _coitus_coverage(spec: dict[str, Any], pilot_shots: list[str]) -> dict[str, Any]:
    pilot_set = {str(s) for s in pilot_shots}
    covered: set[str] = set()
    film_has_meat = False
    by_shot: list[dict[str, Any]] = []
    for scene in spec.get("scenes") or []:
        if not isinstance(scene, dict):
            continue
        for sh in scene.get("shots") or []:
            if not isinstance(sh, dict):
                continue
            dsl = sh.get("dsl") if isinstance(sh.get("dsl"), dict) else {}
            cb = str(sh.get("coitus_beat") or dsl.get("coitus_beat") or "").strip().lower()
            ph = str(sh.get("heat_phase") or dsl.get("heat_phase") or "").strip().lower()
            if cb in MEAT_BEATS or ph in {"act", "climax", "foreplay"}:
                film_has_meat = True
            sid = str(sh.get("id") or "")
            if sid not in pilot_set:
                continue
            tags = sorted({x for x in (cb, ph) if x})
            if tags:
                covered.update(tags)
            by_shot.append({"shot_id": sid, "coitus_beat": cb or None, "heat_phase": ph or None})
    has_undress = bool(covered & {"undress", "foreplay"})
    has_union = bool(covered & {"union", "entry", "lock"})
    has_rhythm = bool(covered & {"rhythm", "act", "finish", "climax"})
    trio_ok = (not film_has_meat) or (has_undress and (has_union or has_rhythm))
    return {
        "film_has_meat": film_has_meat,
        "covered": sorted(covered),
        "has_undress": has_undress,
        "has_union": has_union,
        "has_rhythm": has_rhythm,
        "three_beat_ok": trio_ok,
        "pilot_shots_detail": by_shot,
    }


def _state_index_gaps(root: Path) -> dict[str, Any]:
    try:
        from state_index_gate import run_state_index_check

        report = run_state_index_check(root)
        return {
            "ok": bool(report.get("ok")),
            "gaps": report.get("gaps") or report.get("missing") or report.get("issues") or [],
            "summary": report.get("summary") or report.get("why"),
        }
    except Exception:
        rec = read_json(root / "receipts" / "state-index.json") or {}
        return {
            "ok": rec.get("ok") is not False,
            "gaps": rec.get("gaps") or [],
            "summary": rec.get("summary") or "state-index not run",
            "soft": True,
        }


def _h3_mode_trio(
    root: Path,
    spec: dict[str, Any],
    pilot_shots: list[str],
) -> dict[str, Any]:
    """Suggest pilot coverage for I2V / R2V / T2V (5090 mainline mode GO)."""
    profile = str(spec.get("_i2v_profile") or "").strip().lower()
    h3_block = spec.get("h3") if isinstance(spec.get("h3"), dict) else {}
    h3_on = profile in {"h3_primary", "hybrid_h3"} or h3_block.get("enabled") is True
    by_mode: dict[str, list[dict[str, Any]]] = {"i2v": [], "r2v": [], "t2v": [], "flf": []}
    try:
        from h3_mode import resolve_h3_mode
        from production_router import build_shot_intent
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": True,
            "skipped": True,
            "reason": f"import:{exc}"[:120],
            "h3_enabled": h3_on,
            "profile": profile or None,
        }

    pilot_set = {str(s) for s in pilot_shots}
    film_modes: set[str] = set()
    pilot_modes: set[str] = set()
    for scene in spec.get("scenes") or []:
        if not isinstance(scene, dict):
            continue
        for sh in scene.get("shots") or []:
            if not isinstance(sh, dict) or not sh.get("id"):
                continue
            sid = str(sh["id"])
            try:
                intent = build_shot_intent(spec, sh)
            except Exception:
                intent = {}
            role = str(sh.get("shot_role") or intent.get("shot_role") or "hero")
            has_still = (root / "stills" / f"{sid}.png").is_file() or (
                root / "stills" / f"{sid}.jpg"
            ).is_file()
            has_last = (root / "stills" / f"{sid}_end.png").is_file()
            resolved = resolve_h3_mode(
                sh,
                intent=intent if isinstance(intent, dict) else {},
                has_still=has_still or role == "hero",
                has_last=has_last,
            )
            mode = str(resolved.get("mode") or "i2v").lower()
            if mode not in by_mode:
                mode = "i2v"
            film_modes.add(mode)
            row = {
                "shot_id": sid,
                "mode": mode,
                "alt_mode": resolved.get("alt_mode"),
                "reasons": list(resolved.get("reasons") or [])[:4],
                "in_pilot": sid in pilot_set,
            }
            by_mode[mode].append(row)
            if sid in pilot_set:
                pilot_modes.add(mode)

    picks: dict[str, str | None] = {}
    for mode in ("i2v", "r2v", "t2v", "flf"):
        rows = by_mode.get(mode) or []
        in_p = next((r for r in rows if r.get("in_pilot")), None)
        picks[mode] = str((in_p or (rows[0] if rows else {})).get("shot_id") or "") or None

    need = {"i2v", "t2v"}
    if any(by_mode.get("r2v")):
        need.add("r2v")
    missing = sorted(m for m in need if not picks.get(m))
    cmds: list[str] = []
    for mode, sid in picks.items():
        if not sid:
            continue
        cmds.append(
            f'aifilm h3 run --root "{root}" --shot-id {sid} --mode {mode} --register --stage pilot'
        )
    return {
        "ok": (not missing) if profile == "h3_primary" else True,
        "h3_enabled": h3_on,
        "profile": profile or None,
        "film_modes": sorted(film_modes),
        "pilot_modes": sorted(pilot_modes),
        "picks": picks,
        "missing_modes": missing,
        "by_mode_counts": {k: len(v) for k, v in by_mode.items() if v},
        "pilot_run_cmds": cmds,
        "note": "Mode GO: one I2V + one T2V (env) + R2V if meat energy",
    }


def _go_template(
    root: Path,
    shots: list[str],
    *,
    h3_trio: dict[str, Any] | None = None,
) -> str:
    csv = ",".join(shots)
    lines = [
        "用户 GO 粘贴模板：",
        f'1) aifilm pilot pack --root "{root}"',
        f'2) aifilm pilot score --root "{root}" --shots {csv} '
        f"--score-identity pass --score-style pass --score-motion pass "
        f'--reviewer <you> --notes "…"',
        f'3) aifilm pilot approve --root "{root}" --shots {csv} --user-phrase "pilot 过"',
    ]
    trio = h3_trio if isinstance(h3_trio, dict) else {}
    profile = str(trio.get("profile") or "")
    if trio.get("h3_enabled") or profile in {"h3_primary", "hybrid_h3"}:
        lines.append("4) H3 模式 smoke（I2V / T2V / 可选 R2V）:")
        for cmd in list(trio.get("pilot_run_cmds") or [])[:4]:
            lines.append(f"   {cmd}")
        if profile == "h3_primary":
            lines.append(
                f'5) aifilm h3 cycle --root "{root}" --until-empty --execute  # bulk 挂机'
            )
        else:
            lines.append(
                f'5) aifilm h3 run-next --root "{root}" --execute --max 5  # meat；setup 可 Grok bulk'
            )
    else:
        lines.append("4) media-queue bulk…")
    return "\n".join(lines)


def pilot_pack(root: Path | str, *, shots: list[str] | None = None) -> dict[str, Any]:
    """Build one GO packet and write receipts/pilot-go.json."""
    base = _root(root)
    from pilot_review import pick_pilot_shots, pilot_report
    from production_gates import load_pilot_approval, pilot_is_user_approved

    report = pilot_report(base, shots=shots)
    picked = list(report.get("shots") or [])
    spec = read_json(base / "film-spec.json") or {}
    # Prefer script-value-debrief shortlist (value_rank≥4) when present
    value_pref: dict[str, Any] = {"applied": False}
    try:
        from script_value_debrief import (
            load_debrief,
            map_beats_to_shot_ids,
            merge_pilot_shot_preference,
            pilot_shortlist_from_debrief,
        )

        debrief = load_debrief(base)
        if debrief and not shots:
            mapped = map_beats_to_shot_ids(debrief, spec)
            if mapped:
                suggested = list(report.get("suggested_shots") or pick_pilot_shots(spec))
                merged = merge_pilot_shot_preference(suggested, mapped, n=max(len(suggested), 3))
                # Re-run report with preferred pilot set when caller did not pin shots
                report = pilot_report(base, shots=merged)
                picked = list(report.get("shots") or merged)
                value_pref = {
                    "applied": True,
                    "beat_shortlist": pilot_shortlist_from_debrief(debrief),
                    "mapped_shot_ids": mapped,
                    "merged_shots": merged,
                    "weapon_bias": debrief.get("weapon_bias") or [],
                }
            else:
                value_pref = {
                    "applied": False,
                    "beat_shortlist": pilot_shortlist_from_debrief(debrief),
                    "mapped_shot_ids": [],
                    "reason": "no_shot_map",
                    "weapon_bias": debrief.get("weapon_bias") or [],
                }
    except Exception as exc:  # noqa: BLE001
        value_pref = {"applied": False, "error": str(exc)[:160]}

    heat_scale = str(spec.get("heat_scale") or "").strip().lower()
    coverage = _coitus_coverage(spec, picked)
    state = _state_index_gaps(base)
    heat: dict[str, Any] = {}
    try:
        from heat_check import heat_agent_status

        heat = heat_agent_status(base) or {}
    except Exception as exc:  # noqa: BLE001
        heat = {"error": str(exc)[:160]}

    approval = load_pilot_approval(base)
    approved = pilot_is_user_approved(approval)
    media_ok = bool(report.get("all_media_ready"))
    score_ok = bool(report.get("scorecard_all_pass"))
    trio_ok = bool(coverage.get("three_beat_ok"))
    heat_blocks = bool(heat.get("active") and heat.get("hard_fail"))

    h3_trio = _h3_mode_trio(base, spec if isinstance(spec, dict) else {}, picked)
    profile = str(spec.get("_i2v_profile") or "").strip().lower()

    blockers: list[str] = []
    if not media_ok:
        blockers.append("PILOT_MEDIA_NOT_READY")
    if not score_ok:
        blockers.append("PILOT_SCORECARD_INCOMPLETE")
    if heat_scale in {"max", "hot"} and not trio_ok:
        blockers.append("PILOT_ADULT_THREE_BEAT_MISSING")
    if not approved:
        blockers.append("PILOT_NOT_USER_APPROVED")
    if heat_blocks:
        blockers.append("HEAT_HARD_FAIL")
    if state.get("ok") is False and not state.get("soft"):
        blockers.append("STATE_INDEX_GAPS")
    if (
        profile == "h3_primary"
        and h3_trio.get("missing_modes")
        and os.environ.get("AIFILM_STRICT_H3_PILOT_MODES", "").strip().lower()
        in {"1", "true", "yes", "on"}
    ):
        blockers.append("PILOT_H3_MODE_TRIO_INCOMPLETE")

    ok = not blockers
    next_cmd: str | None = None
    if "PILOT_MEDIA_NOT_READY" in blockers:
        next_cmd = f'aifilm pilot report --root "{base}"  # register pilot stills+clips first'
    elif "PILOT_SCORECARD_INCOMPLETE" in blockers:
        next_cmd = (
            f'aifilm pilot score --root "{base}" --shots {",".join(picked)} '
            "--score-identity pass --score-style pass --score-motion pass "
            '--reviewer <you> --notes "…"'
        )
    elif "PILOT_ADULT_THREE_BEAT_MISSING" in blockers:
        next_cmd = (
            f'aifilm pilot pick --root "{base}"  # re-pick undress+union+rhythm; '
            "re-register those shots into pilot set"
        )
    elif "PILOT_H3_MODE_TRIO_INCOMPLETE" in blockers:
        cmds = list(h3_trio.get("pilot_run_cmds") or [])
        next_cmd = cmds[0] if cmds else f'aifilm h3 list --root "{base}"'
    elif "PILOT_NOT_USER_APPROVED" in blockers:
        next_cmd = (
            f'aifilm pilot approve --root "{base}" --shots {",".join(picked)} '
            '--user-phrase "pilot 过"'
        )
    elif "HEAT_HARD_FAIL" in blockers:
        next_cmd = heat.get("next_cmd") or f'aifilm heat boost --root "{base}" --apply'
    elif "STATE_INDEX_GAPS" in blockers:
        next_cmd = f'aifilm state-index check --root "{base}"'

    bulk_hint = (
        f'aifilm h3 cycle --root "{base}" --until-empty --execute'
        if profile == "h3_primary"
        else f'media-queue add --root "{base}" …  # or h3 run-next'
    )
    payload = {
        "kind": "pilot-go",
        "schema_version": 2,
        "root": str(base),
        "at": utc_now(),
        "ok": ok,
        "pilot_go": {"ok": ok, "blockers": blockers},
        "shots": picked,
        "suggested_shots": report.get("suggested_shots") or pick_pilot_shots(spec),
        "script_value_preference": value_pref,
        "media": report.get("media"),
        "ready_count": report.get("ready_count"),
        "all_media_ready": media_ok,
        "scorecard_all_pass": score_ok,
        "user_approved": approved,
        "adult_three_beat": coverage,
        "h3_mode_trio": h3_trio,
        "state_index": state,
        "heat": {
            "scale": heat_scale,
            "hard_fail": heat.get("hard_fail"),
            "needs_boost": heat.get("needs_boost"),
            "why": heat.get("why"),
            "impact_score": heat.get("impact_score") or heat.get("score"),
        },
        "go_template": _go_template(base, picked, h3_trio=h3_trio),
        "next_cmd": next_cmd,
        "required_proof": blockers[0] if blockers else "pilot_go.ok",
        "next_action": {
            "id": "pilot-go"
            if ok
            else f"pilot-block-{(blockers[0] if blockers else 'unknown').lower()}",
            "cmd": next_cmd or bulk_hint,
            "why": "pilot GO pack ready for bulk" if ok else f"blocked: {','.join(blockers)}",
        },
    }
    path = base / RECEIPT_REL
    write_json(path, payload)
    payload["receipt_path"] = str(path)
    return payload


def load_pilot_go(root: Path | str) -> dict[str, Any] | None:
    data = read_json(_root(root) / RECEIPT_REL)
    return data if isinstance(data, dict) else None


def assert_pilot_go_allows_bulk(root: Path | str, *, force: bool = False) -> dict[str, Any]:
    """Optional thin gate: when pilot-go.json exists, bulk requires ok=true."""
    import os

    if force:
        return {"skipped": True, "reason": "force"}
    if os.environ.get("AIFILM_SKIP_PILOT_GO_GATE", "").strip() in {"1", "true", "yes"}:
        return {"skipped": True, "reason": "env"}
    base = _root(root)
    path = base / RECEIPT_REL
    if not path.is_file():
        return {"skipped": True, "reason": "no_pilot_go_receipt"}
    data = read_json(path) or {}
    if data.get("ok") is True or (data.get("pilot_go") or {}).get("ok") is True:
        return {"ok": True, "pilot_go": data}
    from production_gates import ProductionGateError

    blockers = (data.get("pilot_go") or {}).get("blockers") or data.get("blockers")
    fallback = f'aifilm pilot pack --root "{base}"'
    raise ProductionGateError(
        "pilot-go gate: receipts/pilot-go.json ok=false — "
        f"blockers={blockers}. Next: {data.get('next_cmd') or fallback}"
    )

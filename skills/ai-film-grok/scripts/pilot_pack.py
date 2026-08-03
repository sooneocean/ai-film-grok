"""Pilot GO pack — one-screen evidence before bulk.

Wave A2 · workflow optimize: undress/union/rhythm coverage + media + scorecard
+ approval + heat + state-index gaps → receipts/pilot-go.json.
"""

from __future__ import annotations

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


def _go_template(root: Path, shots: list[str]) -> str:
    csv = ",".join(shots)
    return (
        f"用户 GO 粘贴模板：\n"
        f'1) aifilm pilot pack --root "{root}"\n'
        f'2) aifilm pilot score --root "{root}" --shots {csv} '
        f"--score-identity pass --score-style pass --score-motion pass "
        f'--reviewer <you> --notes "…"\n'
        f'3) aifilm pilot approve --root "{root}" --shots {csv} --user-phrase "pilot 过"\n'
        f"4) media-queue bulk…"
    )


def pilot_pack(root: Path | str, *, shots: list[str] | None = None) -> dict[str, Any]:
    """Build one GO packet and write receipts/pilot-go.json."""
    base = _root(root)
    from pilot_review import pick_pilot_shots, pilot_report
    from production_gates import load_pilot_approval, pilot_is_user_approved

    report = pilot_report(base, shots=shots)
    picked = list(report.get("shots") or [])
    spec = read_json(base / "film-spec.json") or {}
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
    elif "PILOT_NOT_USER_APPROVED" in blockers:
        next_cmd = (
            f'aifilm pilot approve --root "{base}" --shots {",".join(picked)} '
            '--user-phrase "pilot 过"'
        )
    elif "HEAT_HARD_FAIL" in blockers:
        next_cmd = heat.get("next_cmd") or f'aifilm heat boost --root "{base}" --apply'
    elif "STATE_INDEX_GAPS" in blockers:
        next_cmd = f'aifilm state-index check --root "{base}"'

    payload = {
        "kind": "pilot-go",
        "schema_version": 1,
        "root": str(base),
        "at": utc_now(),
        "ok": ok,
        "pilot_go": {"ok": ok, "blockers": blockers},
        "shots": picked,
        "suggested_shots": report.get("suggested_shots") or pick_pilot_shots(spec),
        "media": report.get("media"),
        "ready_count": report.get("ready_count"),
        "all_media_ready": media_ok,
        "scorecard_all_pass": score_ok,
        "user_approved": approved,
        "adult_three_beat": coverage,
        "state_index": state,
        "heat": {
            "scale": heat_scale,
            "hard_fail": heat.get("hard_fail"),
            "needs_boost": heat.get("needs_boost"),
            "why": heat.get("why"),
            "impact_score": heat.get("impact_score") or heat.get("score"),
        },
        "go_template": _go_template(base, picked),
        "next_cmd": next_cmd,
        "required_proof": blockers[0] if blockers else "pilot_go.ok",
        "next_action": {
            "id": "pilot-go"
            if ok
            else f"pilot-block-{(blockers[0] if blockers else 'unknown').lower()}",
            "cmd": next_cmd or f'media-queue add --root "{base}" …  # pilot_go.ok',
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

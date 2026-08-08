#!/usr/bin/env python3
"""Effect-ROI gates: still-feed veto, soft-still lint, effect scorecard, weak-take queue.

Wave E1–E3 (2026-08-07): stop burning H3 on bad stills; multi-axis scorecard;
meat mean floor → reburn list (never pure-mean promote as sole truth).
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from util import read_json, utc_now, write_json
from util.logger import log

RECEIPT_SCORECARD = Path("receipts/effect-scorecard.json")
RECEIPT_REBURN = Path("receipts/weak-take-reburn.json")
MEAN_MEAT_FLOOR = 20.0
MEAN_NORMAL_FLOOR = 18.0

_SOFT_DUAL_THRASH = re.compile(
    r"\b(missionary|doggy|cowgirl|penetrat|double.?penetr|foursome|threesome|"
    r"hardcore\s+sex|full\s+nude\s+duo|explicit\s+sex)\b",
    re.I,
)
_SOFT_HALF_HINT = re.compile(
    r"\b(half.?undress|shirt\s+open|strap(s)?\s+down|shoulder|afterglow|"
    r"半脱|肩线|余韵)\b",
    re.I,
)


def _root(path: Path | str) -> Path:
    return Path(path).expanduser().resolve()


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def still_feed_blocks_h3(root: Path | str) -> dict[str, Any]:
    """E1 · When still feed is hard-red, ban h3-run-next as primary next.

    Blocks on: composition_fill hard, still_face_lock hard, peak wardrobe miss,
    still_source hard. Style-not-locked alone is advisory (pilot path may lock later).
    Escape: AIFILM_SKIP_STILL_FEED_GATE=1
    """
    base = _root(root)
    if _env_truthy("AIFILM_SKIP_STILL_FEED_GATE"):
        try:
            from core.skip_audit import skip_flag

            skip_flag(
                "AIFILM_SKIP_STILL_FEED_GATE",
                origin="env",
                film_root=base,
                call_site="still_feed_blocks_h3",
            )
        except Exception as exc:  # noqa: BLE001
            log.debug(
                "skip audit (AIFILM_SKIP_STILL_FEED_GATE) failed; skip already decided by env: %s",
                exc,
            )
        return {
            "blocked": False,
            "skipped": True,
            "reason": "AIFILM_SKIP_STILL_FEED_GATE",
            "codes": [],
            "next_cmd": None,
            "primary_action": None,
        }

    try:
        from generation_ready import generation_ready_report

        gr = generation_ready_report(base)
    except Exception as exc:  # noqa: BLE001
        return {
            "blocked": False,
            "error": str(exc)[:160],
            "codes": [],
            "next_cmd": None,
            "primary_action": None,
        }

    codes: list[str] = []
    fill_hard = list(gr.get("composition_fill_hard") or [])
    face_hard = list(gr.get("still_face_lock_hard") or [])
    peak = list(gr.get("peak_missing") or [])
    hard = list(gr.get("hard") or [])
    if fill_hard:
        codes.append("COMPOSITION_FILL")
    if face_hard:
        codes.append("STILL_FACE_LOCK")
    if peak:
        codes.append("PEAK_WARDROBE_MISSING")
    if hard:
        codes.append("STILL_SOURCE_HARD")

    blocked = bool(fill_hard or face_hard or peak or hard)
    primary = None
    next_cmd = None
    r = str(base)
    if fill_hard:
        primary = "composition-fill-ensure"
        next_cmd = (
            f'python -c "from composition_fill_gate import audit_film_composition_fill; '
            f"import json; print(json.dumps(audit_film_composition_fill("
            f"'{r}', auto_remedy=True), default=str))\"\n"
            f"# or per-shot: ensure_fill_frame then register-still"
        )
    elif face_hard or hard:
        primary = "still-challenge-repair"
        next_cmd = (
            f'aifilm still-challenge next --root "{r}"\n'
            f"# then register-still --anatomy-safe / face enroll bind"
        )
    elif peak:
        primary = "state-index"
        next_cmd = f'aifilm state-index status --root "{r}"  # peak wardrobe still missing'

    return {
        "blocked": blocked,
        "skipped": False,
        "codes": codes,
        "blockers": list(gr.get("blockers") or [])[:8],
        "generation_ready_ok": bool(gr.get("ok")),
        "composition_fill_ok": bool(gr.get("composition_fill_ok", True)),
        "still_face_lock_ok": bool(gr.get("still_face_lock_ok", True)),
        "line": gr.get("line"),
        "hints": list(gr.get("hints") or [])[:4],
        "primary_action": primary,
        "next_cmd": next_cmd,
        "why": (
            "静帧喂料未绿 — 禁 h3-run-next；先满幅/身份/状态照再烧 H3"
            if blocked
            else "still feed clear for H3"
        ),
    }


def lint_soft_still_recipe(shot: dict[str, Any] | None) -> dict[str, Any]:
    """E1.4 · Soft / cloud-safe still: half-undress · shoulder · afterglow · solo.

    Hard only when heat is soft/hot plot-driven and prompt thrashes dual hardcore.
    Restricted/meat max lanes skip (different grammar).
    """
    if not isinstance(shot, dict):
        return {"ok": True, "skipped": True, "codes": []}
    heat = str(
        shot.get("heat_phase")
        or shot.get("heat_scale")
        or (shot.get("dsl") or {}).get("heat_phase")
        or ""
    ).lower()
    df = str(shot.get("dramatic_function") or "").lower()
    lane_hint = str(shot.get("generation_lane") or shot.get("content_class") or "").lower()
    if any(
        x in lane_hint or x in df or x in heat
        for x in ("meat", "act", "climax", "restricted", "bare", "coitus")
    ):
        return {"ok": True, "skipped": True, "codes": [], "note": "meat/restricted skip soft lint"}

    # Soft still recipe applies to setup / soft intimacy / moderated paths
    softish = (
        heat in {"soft", "warm", "natural", "hot", ""}
        or "setup" in df
        or "approach" in df
        or "afterglow" in df
        or lane_hint in {"setup", "dialogue_safe", "soft", ""}
    )
    if not softish:
        return {"ok": True, "skipped": True, "codes": []}

    blob_parts = [
        str(shot.get("prompt") or ""),
        str(shot.get("still_prompt") or ""),
        str((shot.get("dsl") or {}).get("action") or ""),
        str(shot.get("playable_action") or ""),
        " ".join(str(x) for x in (shot.get("negative_prompt") or []) if x)
        if isinstance(shot.get("negative_prompt"), list)
        else str(shot.get("negative_prompt") or ""),
    ]
    blob = " ".join(blob_parts)
    codes: list[str] = []
    if _SOFT_DUAL_THRASH.search(blob):
        codes.append("SOFT_STILL_DUAL_HARDCORE_THRASH")
    # dual cast without soft framing on soft setup
    casts = shot.get("cast") or shot.get("characters") or []
    if isinstance(casts, list) and len(casts) >= 2 and "setup" in df:
        if not _SOFT_HALF_HINT.search(blob) and _SOFT_DUAL_THRASH.search(blob):
            codes.append("SOFT_STILL_DUAL_NO_HALF_UNDRESS_FRAME")

    hard = "SOFT_STILL_DUAL_HARDCORE_THRASH" in codes
    return {
        "ok": not hard,
        "hard": hard,
        "codes": codes,
        "shot_id": shot.get("id"),
        "note": (
            "soft still: prefer half-undress · shoulder · afterglow face · solo; "
            "ban dual hardcore thrash on soft/setup"
            if codes
            else "soft still recipe ok"
        ),
        "next_cmd": (
            "rewrite still prompt: half-undress shoulder line afterglow solo "
            "(no dual hardcore thrash)"
            if hard
            else None
        ),
    }


def audit_soft_still_film(root: Path | str, *, max_shots: int = 80) -> dict[str, Any]:
    base = _root(root)
    spec = read_json(base / "film-spec.json") or {}
    shots: list[dict[str, Any]] = []
    if isinstance(spec, dict):
        for scene in spec.get("scenes") or []:
            if isinstance(scene, dict):
                for sh in scene.get("shots") or []:
                    if isinstance(sh, dict) and sh.get("id"):
                        shots.append(sh)
        if not shots and isinstance(spec.get("shots"), list):
            shots = [s for s in spec["shots"] if isinstance(s, dict) and s.get("id")]
    issues: list[dict[str, Any]] = []
    for sh in shots[:max_shots]:
        rep = lint_soft_still_recipe(sh)
        if not rep.get("ok"):
            issues.append(rep)
    return {
        "ok": not issues,
        "checked": min(len(shots), max_shots),
        "issues": issues[:20],
        "codes": [c for i in issues for c in (i.get("codes") or [])][:20],
    }


def _shot_list(spec: dict[str, Any]) -> list[dict[str, Any]]:
    shots: list[dict[str, Any]] = []
    for scene in spec.get("scenes") or []:
        if isinstance(scene, dict):
            for sh in scene.get("shots") or []:
                if isinstance(sh, dict) and sh.get("id"):
                    shots.append(sh)
    if not shots and isinstance(spec.get("shots"), list):
        shots = [s for s in spec["shots"] if isinstance(s, dict) and s.get("id")]
    return shots


def _is_meat_shot(sh: dict[str, Any]) -> bool:
    heat = str(sh.get("heat_phase") or "").lower()
    df = str(sh.get("dramatic_function") or "").lower()
    return any(
        x in heat or x in df for x in ("act", "climax", "meat", "coitus", "sex", "union", "rhythm")
    )


def build_effect_scorecard(
    root: Path | str,
    *,
    write: bool = True,
    shortlist: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """E3.1 · Per-shot multi-axis effect card (mean · floor · AH · fill · identity soft)."""
    base = _root(root)
    spec = read_json(base / "film-spec.json") or {}
    shots = _shot_list(spec if isinstance(spec, dict) else {})
    man = read_json(base / "manifest.json") or {}
    clips = man.get("clips") if isinstance(man, dict) and isinstance(man.get("clips"), dict) else {}

    shortlist_rows: dict[str, dict[str, Any]] = {}
    if isinstance(shortlist, dict):
        for row in shortlist.get("shots") or []:
            if isinstance(row, dict) and row.get("shot_id"):
                shortlist_rows[str(row["shot_id"])] = row

    # fill audit soft
    fill_hard_ids: set[str] = set()
    try:
        from composition_fill_gate import audit_film_composition_fill

        cfa = audit_film_composition_fill(base, auto_remedy=False, max_shots=80)
        for h in cfa.get("hard") or []:
            s = str(h)
            # hard entries may be shot ids or codes
            if s and not s.isupper() and " " not in s[:20]:
                fill_hard_ids.add(s.split(":")[0])
    except Exception as exc:  # noqa: BLE001
        log.warning("composition_fill audit failed; assuming ok: %s", exc)
        cfa = {"ok": True}

    rows: list[dict[str, Any]] = []
    weak: list[dict[str, Any]] = []
    pure_mean_risk = 0

    for sh in shots:
        sid = str(sh["id"])
        clip = clips.get(sid) if isinstance(clips.get(sid), dict) else {}
        sl = shortlist_rows.get(sid) or {}
        pref = sl.get("preferred") if isinstance(sl.get("preferred"), dict) else {}
        mean = pref.get("mean")
        if mean is None and isinstance(clip, dict):
            mean = clip.get("mean") or clip.get("mean_absdiff")
        try:
            mean_f = float(mean) if mean is not None else None
        except (TypeError, ValueError):
            mean_f = None

        meat = _is_meat_shot(sh)
        floor = MEAN_MEAT_FLOOR if meat else MEAN_NORMAL_FLOOR
        below = mean_f is not None and mean_f < floor
        hijack = bool(pref.get("composition_hijack")) or (pref.get("composition_ok") is False)
        fill_bad = sid in fill_hard_ids
        ah_note = sl.get("composition_anti_hijack") if isinstance(sl, dict) else None
        multi = int(sl.get("take_count") or 0) >= 2
        if multi and not ah_note and not _env_truthy("AIFILM_SKIP_ANTI_HIJACK"):
            pure_mean_risk += 1

        axes = {
            "mean": mean_f,
            "floor": floor,
            "mean_ok": not below if mean_f is not None else None,
            "meat": meat,
            "anti_hijack_ok": (not hijack) if pref else None,
            "fill_ok": not fill_bad,
            "multi_take": multi,
            "below_floor": below,
            "composition_hijack": hijack,
        }
        effect_ok = True
        if below or hijack or fill_bad:
            effect_ok = False
        row = {
            "shot_id": sid,
            "axes": axes,
            "effect_ok": effect_ok,
            "reburn": below or hijack,
        }
        rows.append(row)
        if below or hijack:
            weak.append(
                {
                    "shot_id": sid,
                    "reason": ("below_mean_floor" if below else "composition_hijack"),
                    "mean": mean_f,
                    "floor": floor,
                    "meat": meat,
                    "priority": "P1" if meat or below else "P2",
                    "next_cmd": (
                        f'aifilm h3 run --root "{base}" --shot-id {sid} --register  # reburn weak take'
                    ),
                }
            )

    # face triple soft attach
    face_master = True
    try:
        from gates.face_lock_triple import audit_face_lock_triple

        trip = audit_face_lock_triple(base, write_receipt=False)
        face_master = bool(trip.get("master_eligible"))
    except Exception as exc:  # noqa: BLE001
        log.warning("face_lock_triple audit failed; assuming master_eligible: %s", exc)
        trip = {"ok": True, "master_eligible": True}

    reburn_payload = {
        "schema_version": 1,
        "kind": "weak-take-reburn",
        "at": utc_now(),
        "root": str(base),
        "count": len(weak),
        "shots": weak[:60],
        "note": "meat mean<20 or AH fail → Fill-Idle P1 reburn; never silent pure-mean promote",
    }
    scorecard = {
        "schema_version": 1,
        "kind": "effect-scorecard",
        "at": utc_now(),
        "root": str(base),
        "ok": not weak and pure_mean_risk == 0 and face_master,
        "shot_count": len(rows),
        "weak_count": len(weak),
        "pure_mean_risk_shots": pure_mean_risk,
        "face_master_eligible": face_master,
        "face_lock_triple": {
            "ok": trip.get("ok"),
            "master_eligible": trip.get("master_eligible"),
            "codes": trip.get("codes") or [],
        },
        "composition_fill_ok": bool(cfa.get("ok", True)),
        "shots": rows[:120],
        "weak_takes": weak[:40],
        "promote_rule": "anti_hijack_before_mean; ban pure-mean multi-seed",
        "next_cmd": (
            f'aifilm h3 run-next --root "{base}" --execute --max 5  # reburn weak' if weak else None
        ),
    }
    if write:
        write_json(base / RECEIPT_SCORECARD, scorecard)
        write_json(base / RECEIPT_REBURN, reburn_payload)
        scorecard["path"] = str(base / RECEIPT_SCORECARD)
        scorecard["reburn_path"] = str(base / RECEIPT_REBURN)
    return scorecard


def assert_face_lock_allows_promote(root: Path | str, *, promote: bool) -> dict[str, Any]:
    """E2.1 · promote=True requires face-lock triple hard legs green (not master_eligible).

    Soft identity_partial still allows promote of clips but marks partial.
    Hard leg fail → promote_blocked.
    Escape: AIFILM_SKIP_FACE_LOCK_PROMOTE=1
    """
    base = _root(root)
    if not promote:
        return {"ok": True, "promote_blocked": False, "skipped": True}
    if _env_truthy("AIFILM_SKIP_FACE_LOCK_PROMOTE"):
        try:
            from core.skip_audit import skip_flag

            skip_flag(
                "AIFILM_SKIP_FACE_LOCK_PROMOTE",
                origin="env",
                film_root=base,
                call_site="assert_face_lock_allows_promote",
            )
        except Exception as exc:  # noqa: BLE001
            log.debug(
                "skip audit (AIFILM_SKIP_FACE_LOCK_PROMOTE) failed; skip already decided by env: %s",
                exc,
            )
        return {"ok": True, "promote_blocked": False, "skipped": True, "reason": "skip env"}

    try:
        from gates.face_lock_triple import audit_face_lock_triple

        trip = audit_face_lock_triple(base, write_receipt=True)
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "promote_blocked": True,
            "codes": ["FACE_LOCK_PROMOTE_PROBE_FAILED"],
            "error": str(exc)[:160],
        }
    hard_legs = list(trip.get("hard_fail_legs") or [])
    blocked = bool(hard_legs) or not bool(trip.get("ok"))
    return {
        "ok": not blocked,
        "promote_blocked": blocked,
        "master_eligible": bool(trip.get("master_eligible")),
        "identity_partial": bool(trip.get("identity_partial")),
        "codes": list(trip.get("codes") or []),
        "hard_fail_legs": hard_legs,
        "next_cmd": trip.get("next_cmd"),
    }


__all__ = [
    "MEAN_MEAT_FLOOR",
    "MEAN_NORMAL_FLOOR",
    "assert_face_lock_allows_promote",
    "audit_soft_still_film",
    "build_effect_scorecard",
    "lint_soft_still_recipe",
    "still_feed_blocks_h3",
]

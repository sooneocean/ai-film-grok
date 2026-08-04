"""Script value debrief — multi-angle pre-lock presentation-value contract.

Receipt: receipts/script-value-debrief.json
Docs: references/script-value-debrief.md
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from util import read_json, utc_now, write_json

RECEIPT_NAME = "script-value-debrief.json"
KIND = "script-value-debrief"
MIN_MUST_KEEP = 2
MIN_VALUE_RANK_PILOT = 4
HIGH_VALUE_FUNCTIONS = frozenset(
    {
        "hook",
        "climax",
        "action",
        "act",
        "approach",
        "afterglow",
        "confrontation",
        "resolution",
    }
)


def receipt_path(root: Path | str) -> Path:
    return Path(root).expanduser().resolve() / "receipts" / RECEIPT_NAME


def load_debrief(root: Path | str) -> dict[str, Any] | None:
    data = read_json(receipt_path(root))
    return data if isinstance(data, dict) else None


def _text(value: object) -> str:
    return str(value or "").strip()


def _as_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def score_promise_clarity(debrief: dict[str, Any]) -> float:
    promise = _text(debrief.get("viewer_promise"))
    open_hook = _text(debrief.get("open_hook"))
    if not promise:
        return 0.0
    score = 0.45
    if len(promise) >= 8:
        score += 0.25
    if open_hook:
        score += 0.30
    return min(1.0, score)


def score_beat_value_coverage(debrief: dict[str, Any]) -> float:
    cards = [c for c in _as_list(debrief.get("beat_cards")) if isinstance(c, dict)]
    if not cards:
        return 0.0
    with_event = sum(1 for c in cards if _text(c.get("visual_event")))
    with_rank = sum(1 for c in cards if c.get("value_rank") is not None)
    with_state = sum(1 for c in cards if _text(c.get("state_in")) and _text(c.get("state_out")))
    n = len(cards)
    return round(
        (with_event / n) * 0.5 + (with_rank / n) * 0.3 + (with_state / n) * 0.2,
        3,
    )


def score_setup_payoff(debrief: dict[str, Any]) -> float:
    writer = _as_dict(debrief.get("writer"))
    pairs = _as_list(writer.get("setup_payoff_pairs") or debrief.get("setup_payoff_pairs"))
    valid = 0
    for p in pairs:
        if not isinstance(p, dict):
            continue
        if _text(p.get("setup_ref")) and _text(p.get("payoff_ref")):
            valid += 1
    if valid >= 2:
        return 1.0
    if valid == 1:
        return 0.7
    # Fallback: climax + ending present in writer
    if _text(writer.get("climax_choice")) and _text(writer.get("ending_hook")):
        return 0.4
    return 0.0


def score_dead_air_awareness(debrief: dict[str, Any]) -> float:
    risks = _as_list(debrief.get("dead_air_risks"))
    hooks = _as_list(debrief.get("retention_hooks"))
    journey = _as_list(debrief.get("audience_journey"))
    score = 0.0
    if risks:
        score += 0.4
    if hooks:
        score += 0.3
    if len(journey) >= 3:
        score += 0.3
    return min(1.0, score)


def score_user_brief(debrief: dict[str, Any]) -> float:
    brief = _as_dict(debrief.get("user_brief"))
    if not brief:
        return 0.0
    score = 0.2
    if _as_list(brief.get("must_have")):
        score += 0.3
    if _as_list(brief.get("must_not")):
        score += 0.2
    if _text(brief.get("success_looks_like") or brief.get("audience_profile")):
        score += 0.3
    return min(1.0, score)


def score_debrief(debrief: dict[str, Any]) -> dict[str, float]:
    dims = {
        "promise_clarity": score_promise_clarity(debrief),
        "beat_value_coverage": score_beat_value_coverage(debrief),
        "setup_payoff_pairs": score_setup_payoff(debrief),
        "dead_air_awareness": score_dead_air_awareness(debrief),
        "user_brief_completeness": score_user_brief(debrief),
    }
    weights = {
        "promise_clarity": 0.25,
        "beat_value_coverage": 0.30,
        "setup_payoff_pairs": 0.20,
        "dead_air_awareness": 0.10,
        "user_brief_completeness": 0.15,
    }
    overall = sum(dims[k] * weights[k] for k in weights)
    dims["overall"] = round(overall, 2)
    return dims


def validate_debrief(
    debrief: dict[str, Any] | None,
    *,
    strict: bool = False,
    require_confirmed: bool = False,
) -> dict[str, Any]:
    """Validate debrief structure.

    Missing debrief → warn (ok=True soft) unless strict → hard fail.
    """
    warnings: list[dict[str, str]] = []
    errors: list[dict[str, str]] = []

    def _err(code: str, msg: str) -> None:
        errors.append({"code": code, "message": msg})

    def _warn(code: str, msg: str) -> None:
        warnings.append({"code": code, "message": msg})

    if not debrief:
        msg = f"missing receipts/{RECEIPT_NAME}"
        if strict:
            _err("DEBRIEF_MISSING", msg)
        else:
            _warn("DEBRIEF_MISSING", msg)
        return {
            "ok": not errors,
            "strict": strict,
            "present": False,
            "errors": errors,
            "warnings": warnings,
            "scores": {},
            "pilot_shortlist_beat_ids": [],
            "weapon_bias": [],
        }

    kind = _text(debrief.get("kind"))
    if kind and kind != KIND:
        _warn("DEBRIEF_KIND_UNEXPECTED", f"kind={kind!r} expected {KIND!r}")

    if not _text(debrief.get("viewer_promise")):
        _err("DEBRIEF_PROMISE_MISSING", "viewer_promise required")

    brief = _as_dict(debrief.get("user_brief"))
    if not brief:
        (_err if strict else _warn)("DEBRIEF_USER_BRIEF_MISSING", "user_brief missing (L0)")
    else:
        if not _as_list(brief.get("must_have")):
            _warn("DEBRIEF_MUST_HAVE_EMPTY", "user_brief.must_have empty")
        if not _as_list(brief.get("must_not")):
            _warn("DEBRIEF_MUST_NOT_EMPTY", "user_brief.must_not empty")

    must_keep = [str(x) for x in _as_list(debrief.get("must_keep_beat_ids")) if str(x).strip()]
    if len(must_keep) < MIN_MUST_KEEP:
        _err(
            "DEBRIEF_MUST_KEEP_FEW",
            f"must_keep_beat_ids need ≥{MIN_MUST_KEEP}, got {len(must_keep)}",
        )

    cards = [c for c in _as_list(debrief.get("beat_cards")) if isinstance(c, dict)]
    if not cards:
        _err("DEBRIEF_BEAT_CARDS_EMPTY", "beat_cards empty")
    else:
        for i, c in enumerate(cards):
            bid = _text(c.get("beat_id")) or f"idx{i}"
            if not _text(c.get("visual_event")):
                _err("DEBRIEF_VISUAL_EVENT_MISSING", f"{bid}: visual_event required")
            rank = c.get("value_rank")
            if rank is None:
                _warn("DEBRIEF_VALUE_RANK_MISSING", f"{bid}: value_rank missing")
            else:
                try:
                    r = int(rank)
                    if r < 1 or r > 5:
                        _warn("DEBRIEF_VALUE_RANK_RANGE", f"{bid}: value_rank {r} not in 1–5")
                except (TypeError, ValueError):
                    _err("DEBRIEF_VALUE_RANK_BAD", f"{bid}: value_rank not int")

    if require_confirmed or (strict and debrief.get("confirmed_by_user") is False):
        if debrief.get("confirmed_by_user") is not True:
            msg = "confirmed_by_user must be true before story lock (strict)"
            if strict or require_confirmed:
                _err("DEBRIEF_NOT_CONFIRMED", msg)
            else:
                _warn("DEBRIEF_NOT_CONFIRMED", msg)
    elif debrief.get("confirmed_by_user") is not True:
        _warn("DEBRIEF_NOT_CONFIRMED", "confirmed_by_user not true — confirm before lock")

    # Adult optional consistency
    adult = debrief.get("adult_note")
    if isinstance(adult, dict) and adult.get("sex_arc_aligned_hard_defaults") is False:
        _warn("DEBRIEF_ADULT_ARC_FLAG", "adult_note.sex_arc_aligned_hard_defaults is false")

    scores = score_debrief(debrief)
    shortlist = pilot_shortlist_from_debrief(debrief)
    weapons = [
        w
        for w in _as_list(debrief.get("weapon_bias"))
        if isinstance(w, dict) and _text(w.get("beat_id"))
    ]

    ok = not errors
    return {
        "ok": ok,
        "strict": strict,
        "present": True,
        "errors": errors,
        "warnings": warnings,
        "scores": scores,
        "pilot_shortlist_beat_ids": shortlist,
        "weapon_bias": weapons,
        "must_keep_beat_ids": must_keep,
        "confirmed_by_user": debrief.get("confirmed_by_user") is True,
    }


def pilot_shortlist_from_debrief(
    debrief: dict[str, Any],
    *,
    min_rank: int = MIN_VALUE_RANK_PILOT,
) -> list[str]:
    """Beat ids for pilot preference: explicit shortlist, else rank≥min, else must_keep."""
    explicit = [
        str(x).strip() for x in _as_list(debrief.get("pilot_shortlist_beat_ids")) if str(x).strip()
    ]
    if explicit:
        return explicit

    ranked: list[tuple[int, str]] = []
    for c in _as_list(debrief.get("beat_cards")):
        if not isinstance(c, dict):
            continue
        bid = _text(c.get("beat_id"))
        if not bid:
            continue
        try:
            rank = int(c.get("value_rank") or 0)
        except (TypeError, ValueError):
            rank = 0
        df = _text(c.get("dramatic_function")).lower()
        if rank >= min_rank or df in HIGH_VALUE_FUNCTIONS:
            ranked.append((rank, bid))
    ranked.sort(key=lambda x: -x[0])
    if ranked:
        return [b for _, b in ranked]

    return [str(x).strip() for x in _as_list(debrief.get("must_keep_beat_ids")) if str(x).strip()]


def map_beats_to_shot_ids(
    debrief: dict[str, Any],
    spec: dict[str, Any],
) -> list[str]:
    """Map shortlist beat_ids → film-spec shot ids when possible.

    Matching order per beat:
    1) shot.id == beat_id
    2) shot.beat_id / dsl.story_beat / dramatic_function contains beat slug
    3) high value_rank cards' dramatic_function → first matching shot
    """
    shortlist = pilot_shortlist_from_debrief(debrief)
    shots: list[dict[str, Any]] = []
    for scene in spec.get("scenes") or []:
        if not isinstance(scene, dict):
            continue
        for sh in scene.get("shots") or []:
            if isinstance(sh, dict) and sh.get("id"):
                shots.append(sh)
    if not shots:
        return []

    by_id = {str(s["id"]): s for s in shots}
    picked: list[str] = []

    def _add(sid: str) -> None:
        if sid and sid not in picked:
            picked.append(sid)

    cards_by_id = {
        _text(c.get("beat_id")): c
        for c in _as_list(debrief.get("beat_cards"))
        if isinstance(c, dict) and _text(c.get("beat_id"))
    }

    for beat_id in shortlist:
        if beat_id in by_id:
            _add(beat_id)
            continue
        card = cards_by_id.get(beat_id) or {}
        df = _text(card.get("dramatic_function")).lower()
        slug = beat_id.lower().replace("beat_", "")
        matched = False
        for sh in shots:
            sid = str(sh["id"])
            dsl = sh.get("dsl") if isinstance(sh.get("dsl"), dict) else {}
            candidates = [
                str(sh.get("beat_id") or ""),
                str(dsl.get("story_beat") or ""),
                str(sh.get("dramatic_function") or ""),
                sid,
            ]
            blob = " ".join(candidates).lower()
            if beat_id.lower() in blob or (slug and slug in blob):
                _add(sid)
                matched = True
                break
            if df and df == str(sh.get("dramatic_function") or "").lower():
                _add(sid)
                matched = True
                break
        if not matched and df:
            for sh in shots:
                if str(sh.get("dramatic_function") or "").lower() == df:
                    _add(str(sh["id"]))
                    break

    return picked


def merge_pilot_shot_preference(
    base_shots: list[str],
    preferred: list[str],
    *,
    n: int | None = None,
) -> list[str]:
    """Prefer debrief-mapped shots first, then fill from base pick order."""
    limit = n if n is not None else max(len(base_shots), len(preferred))
    out: list[str] = []
    for sid in preferred + base_shots:
        if sid and sid not in out:
            out.append(sid)
        if len(out) >= limit:
            break
    return out[:limit] if limit else out


def check_root(
    root: Path | str,
    *,
    strict: bool = False,
    require_confirmed: bool = False,
) -> dict[str, Any]:
    base = Path(root).expanduser().resolve()
    debrief = load_debrief(base)
    report = validate_debrief(debrief, strict=strict, require_confirmed=require_confirmed)
    report["root"] = str(base)
    report["receipt"] = str(receipt_path(base))
    report["kind"] = "script-value-debrief-check"
    report["at"] = utc_now()
    return report


def write_debrief(root: Path | str, debrief: dict[str, Any]) -> Path:
    """Write debrief receipt (agent/CLI helper)."""
    base = Path(root).expanduser().resolve()
    path = receipt_path(base)
    payload = dict(debrief)
    payload.setdefault("kind", KIND)
    payload.setdefault("version", 1)
    payload["written_at"] = utc_now()
    write_json(path, payload)
    return path


def seed_from_reception(
    reception: dict[str, Any],
    *,
    film_title: str | None = None,
) -> dict[str, Any]:
    """Draft debrief from story-reception treatment (agent still fills ranks)."""
    treatment = _as_dict(reception.get("treatment"))
    source = _as_dict(reception.get("source"))
    fidelity = _as_dict(reception.get("fidelity"))
    sha = _text(source.get("sha256"))
    goal = _text(treatment.get("protagonist_goal"))
    opposition = _text(treatment.get("opposition"))
    stakes = _text(treatment.get("stakes"))
    climax = _text(treatment.get("climax_choice"))
    ending = _text(treatment.get("ending_hook"))
    logline = _text(treatment.get("logline"))
    title = film_title or _text(treatment.get("title")) or "untitled"

    scene_beats = _as_list(treatment.get("scene_beats"))
    beat_cards: list[dict[str, Any]] = []
    for i, raw in enumerate(scene_beats[:12], start=1):
        if isinstance(raw, dict):
            label = _text(raw.get("label") or raw.get("name") or raw.get("beat")) or f"beat_{i}"
            ve = _text(raw.get("visual_event") or raw.get("action") or label)
        else:
            label = _text(raw) or f"beat_{i}"
            ve = label
        bid = f"beat_{i:02d}_{_slug(label)}"
        beat_cards.append(
            {
                "beat_id": bid,
                "objective": label,
                "state_in": "tbd",
                "state_out": "tbd",
                "visual_event": ve,
                "visible_change": "",
                "audio_load": "dialogue",
                "value_rank": 3,
                "dramatic_function": "bridge",
            }
        )

    must_keep = [c["beat_id"] for c in beat_cards[:2]] if len(beat_cards) >= 2 else []
    constraints = _as_list(fidelity.get("explicit_constraints"))
    unknowns = list(_as_list(fidelity.get("unknowns")))

    return {
        "kind": KIND,
        "version": 1,
        "film_title": title,
        "source_reception_sha256": sha or None,
        "confirmed_by_user": False,
        "assumptions": ["seeded from story-reception; fill value_rank + must_keep before lock"],
        "user_brief": {
            "audience_profile": "general",
            "platform": "vertical_short",
            "target_duration_sec": 60,
            "must_have": [],
            "must_not": [str(x) for x in constraints if str(x).strip()][:12],
            "success_looks_like": logline or "",
        },
        "writer": {
            "protagonist_goal": goal,
            "opposition": opposition,
            "stakes": stakes,
            "climax_choice": climax,
            "ending_hook": ending,
            "theme_one_line": _text(treatment.get("theme")),
            "information_state": {},
            "setup_payoff_pairs": [],
            "scene_necessity": {},
        },
        "viewer_promise": logline or goal or title,
        "open_hook": _text(treatment.get("camera_intent")) or "",
        "must_keep_beat_ids": must_keep,
        "audience_journey": [],
        "retention_hooks": [],
        "dead_air_risks": [],
        "beat_cards": beat_cards,
        "pilot_shortlist_beat_ids": list(must_keep),
        "weapon_bias": [],
        "compress_candidates": [],
        "provenance": {
            "viewer_promise": "source_supported" if logline else "creative_suggestion",
            "writer.climax_choice": "source_supported" if climax else "creative_suggestion",
        },
        "unknowns": unknowns,
        "adult_note": treatment.get("mature_intimacy")
        if isinstance(treatment.get("mature_intimacy"), dict)
        else None,
        "seeded_from": "story-reception",
    }


def _slug(text: str, fallback: str = "beat") -> str:
    import re

    s = re.sub(r"[^\w\u4e00-\u9fff]+", "_", text.strip().lower())
    s = re.sub(r"_+", "_", s).strip("_")
    return s[:32] if s else fallback


def confirm_debrief(
    root: Path | str,
    *,
    user_phrase: str,
    force: bool = False,
) -> dict[str, Any]:
    """Human sign-off: set confirmed_by_user after structure check."""
    phrase = _text(user_phrase)
    if not phrase:
        raise ValueError("confirm requires non-empty --user-phrase (human sign-off)")
    base = Path(root).expanduser().resolve()
    deb = load_debrief(base)
    if not deb:
        raise FileNotFoundError(f"missing {receipt_path(base)}; seed or write first")
    report = validate_debrief(deb, strict=True, require_confirmed=False)
    structural_errors = [
        e for e in report.get("errors") or [] if e.get("code") != "DEBRIEF_NOT_CONFIRMED"
    ]
    if structural_errors and not force:
        codes = ", ".join(sorted({str(e.get("code")) for e in structural_errors}))
        raise ValueError(f"debrief not structure-valid: {codes}")
    deb["confirmed_by_user"] = True
    deb["confirm_user_phrase"] = phrase
    deb["confirmed_at"] = utc_now()
    path = write_debrief(base, deb)
    final = validate_debrief(deb, strict=True, require_confirmed=True)
    return {
        "ok": final.get("ok"),
        "path": str(path),
        "confirmed_by_user": True,
        "user_phrase": phrase,
        "validation": final,
        "user_summary": user_facing_summary(deb),
        "forced": bool(force and structural_errors),
    }


def user_facing_summary(debrief: dict[str, Any]) -> dict[str, Any]:
    """One-page Chinese-friendly summary for agent to show user (no full JSON dump)."""
    brief = _as_dict(debrief.get("user_brief"))
    must_keep = [str(x) for x in _as_list(debrief.get("must_keep_beat_ids")) if str(x).strip()]
    cards = {
        _text(c.get("beat_id")): c
        for c in _as_list(debrief.get("beat_cards"))
        if isinstance(c, dict) and _text(c.get("beat_id"))
    }
    keep_lines = []
    for bid in must_keep:
        card = cards.get(bid) or {}
        ve = _text(card.get("visual_event")) or _text(card.get("objective")) or bid
        keep_lines.append({"beat_id": bid, "one_liner": ve})
    return {
        "viewer_promise": _text(debrief.get("viewer_promise")),
        "open_hook": _text(debrief.get("open_hook")),
        "must_keep": keep_lines,
        "must_have": list(brief.get("must_have") or []),
        "must_not": list(brief.get("must_not") or []),
        "unknowns": list(debrief.get("unknowns") or []),
        "confirmed_by_user": debrief.get("confirmed_by_user") is True,
        "pilot_shortlist": pilot_shortlist_from_debrief(debrief),
        "beat_count": len(cards),
        "prompt_user": "请确认：确认 / 改 promise / 改 must_have / 改 must_not / 改不可砍 beat",
    }


def attach_to_plan_validate(
    report: dict[str, Any],
    root: Path | str,
    *,
    strict: bool = False,
) -> dict[str, Any]:
    """Merge debrief check into plan validate report."""
    debrief_report = check_root(root, strict=strict)
    report["script_value_debrief"] = debrief_report
    if debrief_report.get("errors"):
        if strict or debrief_report.get("present"):
            report["ok"] = False
            issues = list(report.get("issues") or report.get("errors") or [])
            for e in debrief_report["errors"]:
                issues.append(
                    {
                        "code": e.get("code"),
                        "message": e.get("message"),
                        "source": "script_value_debrief",
                    }
                )
            if "issues" in report or "errors" not in report:
                report["issues"] = issues
            else:
                report["errors"] = issues
    return report

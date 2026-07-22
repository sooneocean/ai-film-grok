#!/usr/bin/env python3
"""Voice-coupled editorial strategy — kill flat hard-hard-hard soup.

Couples **heat_phase + vocal_color + sound_cues + tone_tags** into:

1. re-planned ``edit_craft`` (rhythm grammar, not linear slideshow)
2. per-join ``join_transition_secs`` (snappy hard vs long mood_hold)
3. per-shot ``visual_fit`` / ``cut_on`` (act snaps; afterglow leaves color tail)
4. vocal_color placement hints (offset inside plate)

Film-level switch:

```json
"edit_strategy": {
  "mode": "voice_coupled",   // off | auto | voice_coupled | punchy | silk
  "lock_craft": false,       // true = never replan author edit_craft
  "prefer_vo_fit_on_act": true,
  "hard_join_sec": 0.06,
  "soft_join_sec": 0.26,
  "hold_join_sec": 0.40
}
```

See references/edit-strategy-voice-coupled.md
"""

from __future__ import annotations

from typing import Any

from edit_policy import (
    craft_to_intent_style,
    edit_crafts_to_intents,
    edit_crafts_to_styles,
    normalize_edit_craft,
    suggest_edit_crafts,
)

EDIT_STRATEGY_MODES = frozenset({"off", "auto", "voice_coupled", "punchy", "silk"})

_HARD_FAMILY = frozenset(
    {
        "match_cut",
        "cut_on_action",
        "smash_cut",
        "contrast_cut",
        "insert_cut",
        "montage_jump",
    }
)


class EditStrategyError(ValueError):
    pass


def _heat(shot: dict[str, Any]) -> str:
    hp = str(shot.get("heat_phase") or "").strip().lower()
    if hp:
        return hp
    fn = str(shot.get("dramatic_function") or "").strip().lower()
    if fn in {"hook", "approach"}:
        return "setup"
    if fn in {"sensory", "reaction"}:
        return "foreplay"
    if fn == "action":
        return "act"
    if fn in {"afterglow", "resolution"}:
        return "afterglow"
    return "foreplay"


def _beat(shot: dict[str, Any]) -> str:
    return str(shot.get("dramatic_function") or "").strip().lower()


def _has_color(shot: dict[str, Any]) -> bool:
    if str(shot.get("vocal_color") or "").strip():
        return True
    vc = shot.get("_vocal_color")
    if isinstance(vc, dict) and str(vc.get("text") or "").strip():
        return True
    return False


def _has_cues(shot: dict[str, Any], *keys: str) -> bool:
    cues = shot.get("sound_cues") or []
    if not isinstance(cues, (list, tuple)):
        return False
    low = {str(c).strip().lower() for c in cues}
    return any(k in low for k in keys)


def resolve_edit_strategy(spec: dict[str, Any] | None) -> dict[str, Any]:
    author = (spec or {}).get("edit_strategy") if isinstance(spec, dict) else None
    author = author if isinstance(author, dict) else {}
    mode = str(author.get("mode") or "auto").strip().lower()
    if mode not in EDIT_STRATEGY_MODES:
        mode = "auto"
    heat = str((spec or {}).get("heat_scale") or "").strip().lower()
    if mode == "auto":
        # max/hot adult → voice_coupled; soft → silk
        if heat in {"max", "hot"}:
            mode = "voice_coupled"
        elif heat in {"soft"}:
            mode = "silk"
        else:
            mode = "voice_coupled"
    out = {
        "mode": mode,
        "lock_craft": bool(author.get("lock_craft", False)),
        "prefer_vo_fit_on_act": bool(author.get("prefer_vo_fit_on_act", True)),
        "hard_join_sec": float(author.get("hard_join_sec", 0.06)),
        "soft_join_sec": float(author.get("soft_join_sec", 0.26)),
        "hold_join_sec": float(author.get("hold_join_sec", 0.40)),
        "whip_join_sec": float(author.get("whip_join_sec", 0.18)),
        "color_tail_sec": float(author.get("color_tail_sec", 0.55)),
    }
    # clamp
    for k in ("hard_join_sec", "soft_join_sec", "hold_join_sec", "whip_join_sec"):
        out[k] = max(0.0, min(0.8, float(out[k])))
    return out


def fluency_for_mode(mode: str, heat_scale: str = "") -> str:
    if mode == "punchy":
        return "punchy"
    if mode == "silk":
        return "silk"
    if mode == "voice_coupled":
        # adult: cinematic with punch accents inside craft planner
        return "cinematic" if heat_scale in {"max", "hot"} else "silk"
    return "auto"


def plan_craft_for_join(
    prev: dict[str, Any],
    nxt: dict[str, Any],
    *,
    base_craft: str,
    join_index: int,
    mode: str,
) -> str:
    """Refine a base craft using heat/color/cues."""
    try:
        craft = normalize_edit_craft(base_craft)
    except Exception:
        craft = "soft_glue"

    ph, nh = _heat(prev), _heat(nxt)
    pb, nb = _beat(prev), _beat(nxt)
    color_next = _has_color(nxt)
    color_prev = _has_color(prev)

    # Continue hard family preserved (never dissolve over match)
    chain = ""
    dsl = nxt.get("dsl") if isinstance(nxt.get("dsl"), dict) else {}
    chain = str(dsl.get("chain_mode") or "").strip().lower()
    if chain in {"continue", "match", "match_cut", "byte"}:
        if ph in {"act", "climax"} and nh in {"act", "climax"}:
            return "montage_jump" if join_index % 2 == 0 else "cut_on_action"
        if nh == "climax":
            return "smash_cut"
        if nh == "afterglow":
            return "match_cut"
        return craft if craft in _HARD_FAMILY else "cut_on_action"

    # Heat arc punctuation
    if ph in {"act", "foreplay"} and nh == "act":
        return "montage_jump" if join_index % 2 else "smash_cut"
    if nh == "climax" or (pb == "action" and nb in {"action", "sensory"}):
        return "smash_cut"
    if ph == "climax" and nh == "afterglow":
        return "mood_hold"
    if nh == "afterglow":
        return "mood_hold"
    if ph == "setup" and nh in {"foreplay", "setup"}:
        return "whip_soft" if mode != "punchy" else "smash_cut"

    # Sound-cue driven insert (细节物件)
    if _has_cues(nxt, "leather", "click", "seatbelt", "impact") or _has_cues(
        prev, "leather", "click"
    ):
        if nh in {"foreplay", "act"} and craft not in {"smash_cut", "montage_jump"}:
            return "insert_cut"

    # Vocal color: after emotional peak prefer soft landing into color-heavy shot
    if color_next and nh in {"afterglow", "foreplay"} and ph in {"act", "climax"}:
        return "mood_hold"
    if color_prev and color_next and ph == nh == "act":
        return "montage_jump"

    # Tone: teasing/afterglow → glue; dominant/hungry act → hard
    tones_n = {str(t).lower() for t in (nxt.get("tone_tags") or [])}
    if "afterglow" in tones_n or "shy" in tones_n:
        if craft in _HARD_FAMILY and nh != "climax":
            return "soft_glue"
    if tones_n & {"hungry", "dominant", "moan"} and nh in {"act", "climax"}:
        return "smash_cut" if join_index % 2 else "cut_on_action"

    return craft


def plan_join_transition_secs(
    crafts: list[str],
    *,
    strategy: dict[str, Any],
) -> list[float]:
    hard = float(strategy.get("hard_join_sec", 0.06))
    soft = float(strategy.get("soft_join_sec", 0.26))
    hold = float(strategy.get("hold_join_sec", 0.40))
    whip = float(strategy.get("whip_join_sec", 0.18))
    out: list[float] = []
    for c in crafts:
        try:
            craft = normalize_edit_craft(c)
        except Exception:
            craft = "soft_glue"
        intent, _ = craft_to_intent_style(craft)
        if craft == "mood_hold":
            out.append(hold)
        elif craft == "whip_soft":
            out.append(whip)
        elif craft in {"soft_glue", "scene_bridge"}:
            out.append(soft)
        elif intent == "hard":
            # micro-overlap so hard isn't digital still-cut flash; continue can be 0
            out.append(hard if craft != "match_cut" else min(hard, 0.04))
        else:
            out.append(soft)
    return out


def plan_shot_visual_fit(
    shot: dict[str, Any],
    *,
    strategy: dict[str, Any],
) -> str | None:
    """Return visual_fit override or None to leave author value."""
    if shot.get("visual_fit"):
        return None  # respect author
    if not strategy.get("prefer_vo_fit_on_act", True):
        return None
    hp = _heat(shot)
    # act/climax: snap plate to VO (+ color tail handled by offset, not dead pad)
    if hp in {"act", "climax"}:
        return "vo"
    if hp == "afterglow" and _has_color(shot):
        return "slot"  # keep plate for 呼… tail
    if hp == "setup":
        return "slot"
    return None


def plan_cut_on(shot: dict[str, Any]) -> str | None:
    if not isinstance(shot.get("dsl"), dict):
        return None
    if shot["dsl"].get("cut_on"):
        return None
    hp = _heat(shot)
    if hp in {"act", "climax", "foreplay"}:
        return "mid_motion"
    return None


def plan_color_offset(shot: dict[str, Any], *, strategy: dict[str, Any]) -> float | None:
    if shot.get("vocal_color_offset_sec") is not None:
        try:
            if float(shot["vocal_color_offset_sec"]) >= 0:
                return None
        except (TypeError, ValueError):
            pass
    if not _has_color(shot):
        return None
    try:
        plate = float(shot.get("duration_sec") or 6.0)
    except (TypeError, ValueError):
        plate = 6.0
    hp = _heat(shot)
    tail = float(strategy.get("color_tail_sec", 0.55))
    if hp in {"act", "climax"}:
        # late-mid so 办事 verb lands, then 娇喘
        return max(0.8, plate * 0.52)
    if hp == "afterglow":
        return max(0.4, plate * 0.35)
    return max(0.6, plate * 0.55 - tail * 0.2)


def apply_edit_strategy_to_spec(spec: dict[str, Any]) -> dict[str, Any]:
    """Mutate film-spec: crafts, intents, styles, join secs, per-shot fit."""
    if not isinstance(spec, dict):
        raise EditStrategyError("spec must be dict")
    strategy = resolve_edit_strategy(spec)
    spec["edit_strategy"] = strategy
    mode = strategy["mode"]
    if mode == "off":
        summary = {"ok": True, "mode": "off", "note": "edit_strategy disabled"}
        spec["_edit_strategy_plan"] = summary
        return summary

    scenes = spec.get("scenes")
    if not isinstance(scenes, list):
        return {"ok": False, "error": "no scenes"}

    shots: list[dict[str, Any]] = []
    for sc in scenes:
        if isinstance(sc, dict):
            for s in sc.get("shots") or []:
                if isinstance(s, dict) and s.get("id"):
                    shots.append(s)
    n = len(shots)
    if n < 2:
        summary = {"ok": True, "mode": mode, "n_shots": n, "note": "need ≥2 shots"}
        spec["_edit_strategy_plan"] = summary
        return summary

    heat = str(spec.get("heat_scale") or "")
    flu = fluency_for_mode(mode, heat)

    # Base crafts from beats (or author if lock)
    lock = bool(strategy.get("lock_craft"))
    author_source = str(spec.get("_edit_craft_source") or "")
    if lock and author_source == "author" and isinstance(spec.get("edit_craft"), list):
        crafts = [normalize_edit_craft(c) for c in spec["edit_craft"]]
        craft_source = "author_locked"
    else:
        fns = [_beat(s) for s in shots]
        chains = []
        cuts = []
        focals = []
        vps = []
        for s in shots:
            dsl = s.get("dsl") if isinstance(s.get("dsl"), dict) else {}
            chains.append(str(dsl.get("chain_mode") or ""))
            cuts.append(str(dsl.get("cut_on") or ""))
            focals.append(str(dsl.get("focal_character") or s.get("focal_character") or ""))
            vps.append(str(dsl.get("viewpoint") or ""))
        base = suggest_edit_crafts(
            fns,
            chain_modes=chains,
            cut_ons=cuts,
            fluency=flu,
            focals=focals,
            viewpoints=vps,
        )
        # Voice/heat refine
        crafts = []
        for i, base_c in enumerate(base):
            crafts.append(
                plan_craft_for_join(
                    shots[i],
                    shots[i + 1],
                    base_craft=base_c,
                    join_index=i,
                    mode=mode,
                )
            )
        craft_source = f"strategy:{mode}"

    # Ensure diversity for 60s adult (≥4 craft types soft target)
    if len(set(crafts)) < min(4, len(crafts)) and mode == "voice_coupled":
        crafts = _inject_craft_diversity(crafts, shots)

    intents = edit_crafts_to_intents(crafts)
    styles = edit_crafts_to_styles(crafts)
    join_secs = plan_join_transition_secs(crafts, strategy=strategy)

    spec["edit_craft"] = crafts
    spec["transition_intents"] = intents
    spec["transition_styles"] = styles
    spec["join_transition_secs"] = join_secs
    spec["_edit_craft_source"] = craft_source
    # film-level transition_sec = median soft (legacy single default)
    softs = [s for c, s in zip(crafts, join_secs) if c not in _HARD_FAMILY]
    if softs:
        spec["transition_sec"] = round(sorted(softs)[len(softs) // 2], 3)
    elif mode == "punchy":
        spec["transition_sec"] = strategy["hard_join_sec"]

    fit_changes: list[dict[str, Any]] = []
    for s in shots:
        vf = plan_shot_visual_fit(s, strategy=strategy)
        if vf:
            s["visual_fit"] = vf
            fit_changes.append({"id": s.get("id"), "visual_fit": vf})
        cut = plan_cut_on(s)
        if cut:
            dsl = s.get("dsl") if isinstance(s.get("dsl"), dict) else {}
            dsl = dict(dsl)
            dsl["cut_on"] = cut
            s["dsl"] = dsl
        off = plan_color_offset(s, strategy=strategy)
        if off is not None and _has_color(s):
            s["vocal_color_offset_sec"] = round(float(off), 3)

    summary = {
        "ok": True,
        "mode": mode,
        "fluency": flu,
        "craft_source": craft_source,
        "crafts": crafts,
        "join_transition_secs": join_secs,
        "visual_fit_changes": fit_changes,
        "n_unique_crafts": len(set(crafts)),
        "note": (
            "voice_coupled: act→vo fit + hard micro-joins; "
            "climax smash; afterglow mood_hold; color offset mid-plate"
        ),
    }
    spec["_edit_strategy_plan"] = summary
    return summary


def _inject_craft_diversity(crafts: list[str], shots: list[dict[str, Any]]) -> list[str]:
    """If crafts are too uniform, force insert/smash/montage/mood at heat landmarks."""
    out = list(crafts)
    n = len(out)
    if n < 3:
        return out
    # find first act / climax / afterglow joins
    for i in range(n):
        nh = _heat(shots[i + 1])
        if nh == "act" and out[i] not in _HARD_FAMILY:
            out[i] = "montage_jump"
        if nh == "climax":
            out[i] = "smash_cut"
        if nh == "afterglow":
            out[i] = "mood_hold"
    # force one insert if none
    if "insert_cut" not in out and n >= 4:
        out[max(1, n // 3)] = "insert_cut"
    if "montage_jump" not in out and n >= 5:
        out[min(n - 1, (2 * n) // 3)] = "montage_jump"
    return out

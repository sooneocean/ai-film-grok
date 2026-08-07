#!/usr/bin/env python3
"""Transition / join craft policy — peeled from edit_policy (T5 · 2026-08-07).

Hard-compat: ``edit_policy`` re-exports all public names from this module.
"""

from __future__ import annotations

from typing import Any

from edit_policy_shared import PolicyError

# Inter-shot transition (visual + matching audio acrossfade)
# Slightly longer soft dissolve reads as "丝滑" on vertical short-form
DEFAULT_TRANSITION_SEC = 0.28
MAX_TRANSITION_SEC = 0.60
MIN_TRANSITION_SEC = 0.0
TRANSITION_INTENTS = frozenset({"hard", "soft", "hold"})
# ffmpeg xfade names used for soft/hold (hard = concat)
DEFAULT_XFADE_STYLE = "fade"
SOFT_XFADE_STYLES = frozenset(
    {
        "fade",
        "fadeblack",
        "fadewhite",
        "smoothleft",
        "smoothright",
        "smoothup",
        "smoothdown",
        "hblur",
        "dissolve",
    }
)
# Soft/hold xfade styles that read distinct on 9:16 (avoid soft-soup of only fade)
_STYLE_SOFT_ROTATION = ("smoothleft", "hblur", "smoothup", "dissolve", "fade", "smoothright")
_STYLE_HOLD_ROTATION = ("dissolve", "fadeblack", "hblur", "fade")

def derive_micro_edit_cut(prev_shot: dict[str, Any], cur_shot: dict[str, Any]) -> dict[str, Any]:
    """Derive J-Cut or L-Cut audio overlap parameters between adjacent shots."""
    p_hp = str(prev_shot.get("heat_phase") or prev_shot.get("heatPhase") or "").lower()
    c_hp = str(cur_shot.get("heat_phase") or cur_shot.get("heatPhase") or "").lower()

    if c_hp in {"climax", "act"} and p_hp not in {"climax", "act"}:
        # Entering high tension -> J-Cut (audio leads video)
        return {
            "mode": "j_cut",
            "offset_sec": 0.45,
            "description": "Audio leads video cut into climax",
        }
    elif p_hp in {"climax", "act"} and c_hp not in {"climax", "act"}:
        # Exiting high tension -> L-Cut (audio lingers)
        return {
            "mode": "l_cut",
            "offset_sec": 0.45,
            "description": "Audio lingers past video cut into resolution",
        }
    elif p_hp == "climax" and c_hp == "climax":
        # Rapid climax cuts -> alternating J-Cut / L-Cut
        sid_num = sum(ord(ch) for ch in str(cur_shot.get("id") or "0"))
        mode = "j_cut" if sid_num % 2 == 0 else "l_cut"
        return {"mode": mode, "offset_sec": 0.35, "description": f"Alternating {mode} in climax"}

    return {"mode": "standard", "offset_sec": 0.0, "description": "Standard concurrent cut"}

def normalize_transition_sec(value: object | None) -> float:
    if value is None:
        return DEFAULT_TRANSITION_SEC
    try:
        sec = float(value)
    except (TypeError, ValueError) as exc:
        raise PolicyError("transition_sec must be a number") from exc
    if sec < MIN_TRANSITION_SEC or sec > MAX_TRANSITION_SEC:
        raise PolicyError(f"transition_sec must be in [{MIN_TRANSITION_SEC}, {MAX_TRANSITION_SEC}]")
    return sec


def _join_use_t(transition_sec: float, cursor: float, next_dur: float) -> float:
    """Per-join overlap used by video xfade (and matching audio acrossfade)."""
    t = float(transition_sec)
    if t <= 0:
        return 0.0
    use_t = min(t, cursor * 0.45, float(next_dur) * 0.45)
    if use_t < 0.05:
        # match build_xfade floor so tiny segments still get a defined transition
        use_t = 0.05
    return use_t


def normalize_transition_intent(value: object, *, field: str = "transition intent") -> str:
    if not isinstance(value, str) or not value.strip():
        raise PolicyError(f"{field} must be one of {sorted(TRANSITION_INTENTS)}")
    intent = value.strip().lower()
    if intent not in TRANSITION_INTENTS:
        raise PolicyError(f"{field} must be one of {sorted(TRANSITION_INTENTS)}; got {value!r}")
    return intent


def intent_to_base_sec(
    intent: str,
    default_sec: float,
    *,
    fluency: str = "auto",
) -> float:
    """Map hard/soft/hold to nominal overlap seconds (before segment clamps)."""
    intent = normalize_transition_intent(intent)
    d = float(default_sec) if default_sec and float(default_sec) > 0 else DEFAULT_TRANSITION_SEC
    flu = (fluency or "auto").strip().lower()
    if intent == "hard":
        return 0.0
    if intent == "hold":
        # longer dissolve / hold-class join — silky residual mood
        base = min(MAX_TRANSITION_SEC, max(d * 1.65, 0.42))
        if flu == "silk":
            return min(MAX_TRANSITION_SEC, max(base, 0.48))
        return base
    # soft — full default dissolve; silk slightly longer for editorial glue
    soft = min(MAX_TRANSITION_SEC, max(d, 0.22))
    if flu == "silk":
        return min(MAX_TRANSITION_SEC, max(soft, min(d * 1.15, 0.38)))
    return soft


def normalize_xfade_style(value: object | None) -> str:
    """Validate optional film-spec transition_style for soft/hold joins."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return DEFAULT_XFADE_STYLE
    if not isinstance(value, str):
        raise PolicyError("transition_style must be a string")
    style = value.strip().lower()
    if style not in SOFT_XFADE_STYLES:
        raise PolicyError(
            f"transition_style must be one of {sorted(SOFT_XFADE_STYLES)}; got {value!r}"
        )
    return style


# ---------------------------------------------------------------------------
# Editorial craft (资深剪辑语法 · 2026-07-20)
# Maps senior-editor join *ideas* → hard|soft|hold + xfade style.
# Continue seams always collapse to match_cut / cut_on_action (hard).
# Full grammar: references/editorial-craft.md
# ---------------------------------------------------------------------------
EDIT_CRAFTS = frozenset(
    {
        "match_cut",  # byte-identical continue hard
        "cut_on_action",  # mid-motion hard continue
        "smash_cut",  # shock energy hard
        "contrast_cut",  # size/axis/power flip hard
        "insert_cut",  # detail insert hard
        "montage_jump",  # parallel / action burst hard
        "soft_glue",  # scene-interior silk soft
        "whip_soft",  # directional energy soft (hblur/smooth*)
        "speed_ramp",  # kinetic energy ramp transition
        "mood_hold",  # afterglow landing hold
        "scene_bridge",  # cross-scene soft/hold
    }
)

# craft → (intent, preferred soft style or "hard")
_CRAFT_TO_JOIN: dict[str, tuple[str, str]] = {
    "match_cut": ("hard", "hard"),
    "cut_on_action": ("hard", "hard"),
    "smash_cut": ("hard", "hard"),
    "contrast_cut": ("hard", "hard"),
    "insert_cut": ("hard", "hard"),
    "montage_jump": ("hard", "hard"),
    "soft_glue": ("soft", "dissolve"),
    "whip_soft": ("soft", "hblur"),
    "speed_ramp": ("soft", "smoothright"),
    "mood_hold": ("hold", "fadeblack"),
    "scene_bridge": ("soft", "fadeblack"),
}

_CRAFT_WHY: dict[str, str] = {
    "match_cut": "continue 字节接戏 hard match-cut",
    "cut_on_action": "动作中切 hard（动能连续）",
    "smash_cut": "情绪/动作冲击 hard 砸切",
    "contrast_cut": "景别/权力/轴线对比 hard",
    "insert_cut": "细节插入硬切（感官物件）",
    "montage_jump": "蒙太奇/连打动作 hard 跳切",
    "soft_glue": "场内情绪连续 soft 胶水",
    "whip_soft": "方向性能量 soft（whip/hblur 感）",
    "speed_ramp": "动能变速切 soft（尾端加速+首端落点）",
    "mood_hold": "余韵着陆 hold 长叠",
    "scene_bridge": "跨场景桥 soft/fadeblack",
}


def normalize_edit_craft(value: object, *, field: str = "edit_craft") -> str:
    if not isinstance(value, str) or not value.strip():
        raise PolicyError(f"{field} must be one of {sorted(EDIT_CRAFTS)}")
    craft = value.strip().lower().replace("-", "_").replace(" ", "_")
    # aliases
    aliases = {
        "match": "match_cut",
        "matchcut": "match_cut",
        "action_cut": "cut_on_action",
        "cut_on": "cut_on_action",
        "smash": "smash_cut",
        "contrast": "contrast_cut",
        "insert": "insert_cut",
        "montage": "montage_jump",
        "jump_cut": "montage_jump",
        "glue": "soft_glue",
        "soft": "soft_glue",
        "whip": "whip_soft",
        "hold": "mood_hold",
        "landing": "mood_hold",
        "bridge": "scene_bridge",
        "l_cut": "soft_glue",  # audio L/J is default continuous mix; visual glue
        "j_cut": "soft_glue",
    }
    craft = aliases.get(craft, craft)
    if craft not in EDIT_CRAFTS:
        raise PolicyError(f"{field} must be one of {sorted(EDIT_CRAFTS)}; got {value!r}")
    return craft


def craft_to_intent_style(craft: str) -> tuple[str, str]:
    """Map edit craft → (transition_intent, xfade_style_or_hard)."""
    c = normalize_edit_craft(craft)
    return _CRAFT_TO_JOIN[c]


def suggest_edit_craft(
    prev_beat: str,
    next_beat: str,
    *,
    next_chain_mode: str | None = None,
    next_cut_on: str | None = None,
    cross_scene: bool = False,
    fluency: str = "auto",
    join_index: int = 0,
    focal_changed: bool = False,
    next_viewpoint: str | None = None,
) -> str:
    """Pick a senior-editor craft for the join between two shots.

    Non-linear *grammar* (not random): shock vs glue vs landing vs insert,
    while continue seams always hard-family. Character stance shifts
    (focal/viewpoint) escalate to reverse/contrast/smash energy.
    """
    prev_b = (prev_beat or "").strip().lower()
    next_b = (next_beat or "").strip().lower()
    chain = (next_chain_mode or "").strip().lower()
    cut_on = (next_cut_on or "").strip().lower()
    flu = (fluency or "auto").strip().lower()
    nvp = (next_viewpoint or "").strip().lower()
    if flu not in {"auto", "silk", "punchy", "cinematic"}:
        flu = "auto"

    # --- Rhythmic Editing (Action/Climax Accents) ---
    if next_b in {"action", "climax"}:
        if cross_scene:
            return "smash_cut"
        if chain in {"continue", "match", "match_cut", "byte"} or cut_on in {
            "action",
            "mid-action",
            "mid_motion",
        }:
            return "cut_on_action"
        if flu == "punchy":
            return "smash_cut"

    # Character stance: focal flip → reverse/contrast energy (still hard on continue)
    if focal_changed and nvp in {"reverse", "reaction_to", "ots"}:
        if chain in {"continue", "match", "match_cut", "byte"}:
            return "contrast_cut" if nvp == "reverse" else "smash_cut"
        return "contrast_cut" if nvp == "reverse" else "smash_cut"
    if focal_changed and not chain:
        return "contrast_cut"
    # P2/P3: continue = always HARD, but label *why* (anti-flat craft vocabulary)
    # smash/insert/montage still map to intent=hard — no dissolve on byte seams.
    if chain in {"continue", "match", "match_cut", "byte"}:
        if next_b == "afterglow":
            return (
                "cut_on_action" if cut_on in {"mid_motion", "mid-action", "action"} else "match_cut"
            )
        if prev_b == "action" and next_b == "reaction":
            return "smash_cut"
        if prev_b == "action" and next_b == "action":
            return "montage_jump"
        if next_b == "sensory" or prev_b == "sensory":
            return "insert_cut"
        if prev_b == "sensory" and next_b == "reaction":
            return "contrast_cut"
        if nvp == "reaction_to":
            return "smash_cut"
        if cut_on in {"mid_motion", "mid-action", "action"}:
            return "cut_on_action"
        return "match_cut"
    # Cross-scene bridge (导演场景边界)
    if cross_scene:
        if next_b == "afterglow":
            return "mood_hold"
        return "scene_bridge" if flu != "punchy" else "smash_cut"
    # Viewpoint-driven joins (non-continue)
    if nvp == "reverse":
        return "contrast_cut"
    if nvp == "reaction_to":
        return "smash_cut"
    if nvp == "insert_object" or next_b == "sensory":
        return "insert_cut"
    # Shock / energy punctuation
    if prev_b == "action" and next_b == "reaction":
        return "smash_cut"
    if prev_b == "sensory" and next_b == "reaction":
        return "contrast_cut"
    if prev_b == "action" and next_b == "action":
        return "montage_jump"
    if prev_b == "hook" and next_b in ("action", "approach"):
        return "smash_cut" if flu in {"punchy", "cinematic", "auto"} else "whip_soft"
    if prev_b == "action" and next_b == "sensory":
        return "insert_cut" if flu != "silk" else "whip_soft"
    if prev_b in ("approach", "action") and next_b == "sensory":
        return "insert_cut"
    # Landings
    if next_b == "afterglow" or (prev_b == "reaction" and next_b == "afterglow"):
        return "mood_hold"
    if prev_b == "afterglow" and next_b in ("bridge", "afterglow"):
        return "mood_hold"
    # Directional energy
    if prev_b in ("approach", "hook") and next_b in ("action", "sensory"):
        return "whip_soft" if flu in {"silk", "cinematic", "auto"} else "smash_cut"
    if prev_b == "reaction" and next_b in ("action", "approach"):
        return "smash_cut" if flu == "punchy" else "whip_soft"
    # Continuous interior flow
    if prev_b in ("hook", "bridge", "approach") and next_b in ("approach", "sensory", "action"):
        return "soft_glue" if flu != "punchy" else "whip_soft"
    if prev_b == "sensory" and next_b in ("action", "sensory"):
        return "soft_glue" if next_b == "sensory" else "whip_soft"
    if flu == "punchy":
        return "montage_jump" if join_index % 3 == 0 else "smash_cut"
    if flu in {"silk", "cinematic"}:
        return "soft_glue"
    return "soft_glue"


def suggest_edit_crafts(
    dramatic_functions: list[str],
    *,
    chain_modes: list[str] | None = None,
    cut_ons: list[str] | None = None,
    scene_ids: list[str | int] | None = None,
    fluency: str = "auto",
    focals: list[str] | None = None,
    viewpoints: list[str] | None = None,
) -> list[str]:
    """Build n_shots-1 edit crafts (senior editor plan for write-spec)."""
    fns = [(f or "").strip().lower() for f in dramatic_functions]
    if len(fns) < 2:
        return []
    chains = list(chain_modes or [])
    cuts = list(cut_ons or [])
    scenes = list(scene_ids or [])
    foc = [str(x or "").strip().lower() for x in (focals or [])]
    vps = [(v or "").strip().lower() for v in (viewpoints or [])]
    out: list[str] = []
    for i in range(len(fns) - 1):
        next_chain = chains[i + 1] if i + 1 < len(chains) else None
        next_cut = cuts[i + 1] if i + 1 < len(cuts) else None
        cross = False
        if scenes and i + 1 < len(scenes):
            cross = str(scenes[i]) != str(scenes[i + 1])
        focal_changed = False
        if foc and i + 1 < len(foc):
            focal_changed = foc[i] != foc[i + 1]
        next_vp = vps[i + 1] if i + 1 < len(vps) else None
        out.append(
            suggest_edit_craft(
                fns[i],
                fns[i + 1],
                next_chain_mode=next_chain,
                next_cut_on=next_cut,
                cross_scene=cross,
                fluency=fluency,
                join_index=i,
                focal_changed=focal_changed,
                next_viewpoint=next_vp,
            )
        )
    # Anti-linear: never allow 4+ consecutive soft_glue without a hard craft
    return _punctuate_soft_run(out, fluency=fluency)


def _punctuate_soft_run(crafts: list[str], *, fluency: str = "auto") -> list[str]:
    """Insert hard punctuation so the cut rhythm is not flat soft soup."""
    if not crafts:
        return crafts
    softish = {"soft_glue", "whip_soft", "mood_hold", "scene_bridge"}
    hardish = {
        "match_cut",
        "cut_on_action",
        "smash_cut",
        "contrast_cut",
        "insert_cut",
        "montage_jump",
    }
    run = 0
    out: list[str] = []
    max_soft_run = 1 if fluency == "punchy" else 2
    for c in crafts:
        if c in softish:
            run += 1
            if run > max_soft_run and c == "soft_glue":
                out.append("contrast_cut")
                run = 0
                continue
        else:
            run = 0 if c in hardish else run
        out.append(c)
    return out


def edit_crafts_to_intents(crafts: list[str]) -> list[str]:
    return [craft_to_intent_style(c)[0] for c in crafts]


def edit_crafts_to_styles(crafts: list[str], *, soft_i_start: int = 0) -> list[str]:
    """Map crafts to per-join xfade styles (hard → fade placeholder)."""
    styles: list[str] = []
    soft_i = soft_i_start
    for i, craft in enumerate(crafts):
        intent, preferred = craft_to_intent_style(craft)
        if intent == "hard":
            styles.append("fade")
            continue
        if craft == "whip_soft":
            styles.append(("hblur", "smoothleft", "smoothright", "smoothup")[soft_i % 4])
            soft_i += 1
        elif craft == "mood_hold":
            styles.append(_STYLE_HOLD_ROTATION[i % len(_STYLE_HOLD_ROTATION)])
        elif craft == "scene_bridge":
            styles.append("fadeblack" if soft_i % 2 == 0 else "dissolve")
            soft_i += 1
        elif preferred in SOFT_XFADE_STYLES:
            # rotate if many dissolves
            if preferred == "dissolve":
                styles.append(_STYLE_SOFT_ROTATION[soft_i % len(_STYLE_SOFT_ROTATION)])
                soft_i += 1
            else:
                styles.append(preferred)
        else:
            styles.append(_STYLE_SOFT_ROTATION[soft_i % len(_STYLE_SOFT_ROTATION)])
            soft_i += 1
    return styles


def suggest_join_intent(
    prev_beat: str,
    next_beat: str,
    *,
    next_chain_mode: str | None = None,
    fluency: str = "auto",
    next_cut_on: str | None = None,
    cross_scene: bool = False,
    join_index: int = 0,
) -> str:
    """Pick hard|soft|hold via edit craft catalog (senior editor grammar).

    **continue chain**: always **hard** (match_cut / cut_on_action).
    **fluency=silk|cinematic**: more soft/hold glue on non-continue.
    **fluency=punchy**: more smash/montage hard punctuation.
    """
    craft = suggest_edit_craft(
        prev_beat,
        next_beat,
        next_chain_mode=next_chain_mode,
        next_cut_on=next_cut_on,
        cross_scene=cross_scene,
        fluency=fluency,
        join_index=join_index,
    )
    return craft_to_intent_style(craft)[0]


def suggest_transition_intents(
    dramatic_functions: list[str],
    *,
    chain_modes: list[str] | None = None,
    fluency: str = "auto",
    cut_ons: list[str] | None = None,
    scene_ids: list[str | int] | None = None,
) -> list[str]:
    """Build n_shots-1 join intents from beat sequence (for write-spec auto-fill).

    chain_modes[i] is the *incoming* shot's dsl.chain_mode (index matches shot i).
    Join i is between shot i and shot i+1 → use chain_modes[i+1] when present.
    Uses editorial craft catalog (see suggest_edit_crafts).
    """
    crafts = suggest_edit_crafts(
        dramatic_functions,
        chain_modes=chain_modes,
        cut_ons=cut_ons,
        scene_ids=scene_ids,
        fluency=fluency,
    )
    return edit_crafts_to_intents(crafts)


def enforce_continue_hard_joins(
    intents: list[str],
    chain_modes: list[str] | None,
) -> tuple[list[str], list[dict[str, Any]]]:
    """Force hard match-cut on continue joins even when author wrote soft/hold.

    Join i is between shot i and shot i+1 → uses chain_modes[i+1] (incoming).
    Returns (new_intents, fix_notes).
    """
    if not intents:
        return [], []
    chains = list(chain_modes or [])
    out: list[str] = []
    notes: list[dict[str, Any]] = []
    for i, intent in enumerate(intents):
        it = normalize_transition_intent(intent, field=f"transition_intents[{i}]")
        next_chain = chains[i + 1] if i + 1 < len(chains) else ""
        chain = (next_chain or "").strip().lower()
        if chain in {"continue", "match", "match_cut", "byte"} and it != "hard":
            notes.append(
                {
                    "join_index": i,
                    "from": it,
                    "to": "hard",
                    "reason": (
                        f"chain_mode={chain!r} → hard match-cut "
                        "(forbid dissolve on continue; 男娘/胃镜室教训)"
                    ),
                }
            )
            out.append("hard")
        else:
            out.append(it)
    return out, notes


def suggest_transition_styles(
    join_intents: list[str],
    *,
    dramatic_functions: list[str] | None = None,
    edit_crafts: list[str] | None = None,
) -> list[str]:
    """Per-join xfade style names (length = len(join_intents)).

    Prefer edit_crafts mapping when provided (senior editor).
    hard → fade (unused by ffmpeg concat path but keeps array aligned)
    soft/hold → rotate styles so 60s films don't look like one dissolve soup
    """
    if edit_crafts is not None and len(edit_crafts) == len(join_intents):
        return edit_crafts_to_styles(edit_crafts)

    styles: list[str] = []
    soft_i = 0
    hold_i = 0
    fns = [(f or "").strip().lower() for f in (dramatic_functions or [])]
    for i, intent in enumerate(join_intents):
        it = normalize_transition_intent(intent, field=f"join_intents[{i}]")
        if it == "hard":
            styles.append("fade")
            continue
        # Directional bias from approach/action when possible
        prev_b = fns[i] if i < len(fns) else ""
        next_b = fns[i + 1] if i + 1 < len(fns) else ""
        if it == "hold":
            styles.append(_STYLE_HOLD_ROTATION[hold_i % len(_STYLE_HOLD_ROTATION)])
            hold_i += 1
            continue
        # soft
        if prev_b == "approach" or next_b == "approach":
            styles.append("smoothleft")
        elif prev_b == "action" or next_b == "action":
            styles.append("hblur" if soft_i % 2 == 0 else "smoothup")
        elif prev_b == "sensory" or next_b == "sensory":
            styles.append("dissolve")
        else:
            styles.append(_STYLE_SOFT_ROTATION[soft_i % len(_STYLE_SOFT_ROTATION)])
        soft_i += 1
    return styles


def normalize_transition_styles(
    styles: list[object] | None,
    *,
    n_joins: int,
    fallback: str = DEFAULT_XFADE_STYLE,
) -> list[str]:
    """Validate length n_joins; each entry is a SOFT_XFADE_STYLES name."""
    if styles is None:
        return [normalize_xfade_style(fallback)] * max(0, n_joins)
    if not isinstance(styles, list):
        raise PolicyError("transition_styles must be an array of xfade style names")
    if len(styles) != n_joins:
        raise PolicyError(
            f"transition_styles length must be {n_joins} (n_shots-1); got {len(styles)}"
        )
    out: list[str] = []
    for i, s in enumerate(styles):
        try:
            out.append(normalize_xfade_style(s))
        except PolicyError as exc:
            raise PolicyError(f"transition_styles[{i}]: {exc}") from exc
    return out


def resolve_join_use_ts(
    segment_durs: list[float],
    *,
    default_sec: float,
    join_intents: list[str] | None = None,
) -> tuple[list[float], list[str]]:
    """Per-join use_t list matching segment_durs (length n-1)."""
    durs = [float(d) for d in segment_durs]
    n = len(durs)
    if n <= 1:
        return [], []
    if join_intents is None:
        intents = ["soft"] * (n - 1) if default_sec > 0 else ["hard"] * (n - 1)
    else:
        if len(join_intents) != n - 1:
            raise PolicyError(
                f"join_intents length must be {n - 1} for {n} segments; got {len(join_intents)}"
            )
        intents = [
            normalize_transition_intent(x, field=f"join_intents[{i}]")
            for i, x in enumerate(join_intents)
        ]
    use_ts: list[float] = []
    cursor = durs[0]
    for i in range(1, n):
        base = intent_to_base_sec(intents[i - 1], default_sec)
        use_t = 0.0 if base <= 0 else _join_use_t(base, cursor, durs[i])
        use_ts.append(use_t)
        cursor = cursor + durs[i] - use_t
    return use_ts, intents


def expand_story_join_intents(
    n_shots: int,
    *,
    story_intents: list[str] | None,
    default_intent: str = "soft",
    edge_intent: str = "soft",
) -> list[str]:
    """Expand story-shot joins into full title+shots+end join list (n_shots+1 intents)."""
    if n_shots < 1:
        raise PolicyError("need at least one story shot")
    default_intent = normalize_transition_intent(default_intent, field="default transition intent")
    edge_intent = normalize_transition_intent(edge_intent, field="edge transition intent")
    between: list[str]
    if story_intents is None:
        between = [default_intent] * max(0, n_shots - 1)
    else:
        if len(story_intents) != max(0, n_shots - 1):
            raise PolicyError(
                f"transition_intents length must be n_shots-1={max(0, n_shots - 1)}; "
                f"got {len(story_intents)}"
            )
        between = [
            normalize_transition_intent(x, field=f"transition_intents[{i}]")
            for i, x in enumerate(story_intents)
        ]
    # joins: title→s0, s0→s1, ..., sLast→end
    return [edge_intent] + between + [edge_intent]


def expand_story_join_styles(
    n_shots: int,
    *,
    story_styles: list[str] | None,
    edge_style: str = DEFAULT_XFADE_STYLE,
) -> list[str]:
    """Expand story-shot xfade styles into full title+shots+end list (n_shots+1 styles)."""
    if n_shots < 1:
        raise PolicyError("need at least one story shot")
    edge = normalize_xfade_style(edge_style)
    n_between = max(0, n_shots - 1)
    if story_styles is None:
        between = [edge] * n_between
    else:
        between = normalize_transition_styles(story_styles, n_joins=n_between, fallback=edge)
    # title→shot0, between shots, last→endcard
    return [edge, *between, edge]


def segment_timeline(
    segment_durs: list[float],
    transition_sec: float,
    *,
    join_intents: list[str] | None = None,
    join_use_ts: list[float] | None = None,
) -> dict[str, Any]:
    """Final-timeline starts for each segment under successive xfade/acrossfade.

    Segment i begins on the output clock at starts[i]. With transitions enabled,
    starts[i+1] == starts[i] + durs[i] - use_ts[i] (overlap), not a hard sum.
    Subtitles, native stems, and VO must use these starts — not cumulative hard targets.

    join_intents / join_use_ts enable per-join hard|soft|hold (P2).
    """
    if not segment_durs:
        raise PolicyError("need at least one segment")
    durs = [float(d) for d in segment_durs]
    n = len(durs)
    t = float(transition_sec)

    if join_use_ts is not None:
        if len(join_use_ts) != max(0, n - 1):
            raise PolicyError("join_use_ts length must be n_segments-1")
        use_ts = [max(0.0, float(u)) for u in join_use_ts]
        intents = join_intents
    elif n == 1:
        use_ts = []
        intents = []
    else:
        use_ts, intents = resolve_join_use_ts(durs, default_sec=t, join_intents=join_intents)

    starts = [0.0]
    cursor = durs[0]
    for i in range(1, n):
        use_t = use_ts[i - 1] if use_ts else 0.0
        if use_t <= 0:
            starts.append(cursor)
            cursor = cursor + durs[i]
        else:
            offset = max(0.0, cursor - use_t)
            starts.append(offset)
            cursor = cursor + durs[i] - use_t

    enabled = any(u > 1e-9 for u in use_ts)
    return {
        "starts": starts,
        "use_ts": use_ts,
        "join_intents": list(intents) if intents is not None else None,
        "output_duration": cursor if n else 0.0,
        "enabled": enabled,
        "n_inputs": n,
        "transition_sec": t,
    }


def film_segment_timeline(
    *,
    title_duration: float,
    shot_targets: list[float],
    end_duration: float,
    transition_sec: float,
    story_join_intents: list[str] | None = None,
    default_intent: str = "soft",
    edge_intent: str = "soft",
) -> dict[str, Any]:
    """Timeline for title + story shots + end (same order as final concat)."""
    durs = [float(title_duration)] + [float(x) for x in shot_targets] + [float(end_duration)]
    n_shots = len(shot_targets)
    full_intents = expand_story_join_intents(
        n_shots,
        story_intents=story_join_intents,
        default_intent=default_intent if transition_sec > 0 else "hard",
        edge_intent=edge_intent if transition_sec > 0 else "hard",
    )
    tl = segment_timeline(durs, transition_sec, join_intents=full_intents)
    shot_starts = tl["starts"][1 : 1 + n_shots]
    return {
        **tl,
        "segment_durs": durs,
        "shot_starts": shot_starts,
        "title_duration": float(title_duration),
        "end_duration": float(end_duration),
        "story_join_intents": story_join_intents,
        "full_join_intents": full_intents,
    }


def xfade_output_duration(
    segment_durs: list[float],
    transition_sec: float,
    *,
    join_intents: list[str] | None = None,
) -> float:
    """Total duration after successive xfade of equal transition length."""
    if not segment_durs:
        return 0.0
    return float(
        segment_timeline(segment_durs, transition_sec, join_intents=join_intents)["output_duration"]
    )


def build_xfade_filter_graph(
    segment_durs: list[float],
    *,
    transition_sec: float = DEFAULT_TRANSITION_SEC,
    transition: str = "fade",
    join_intents: list[str] | None = None,
    join_use_ts: list[float] | None = None,
    join_styles: list[str] | None = None,
) -> dict[str, Any]:
    """Build ffmpeg filter_complex for N video inputs with mixed hard/soft joins.

    Returns {filter_complex, output_label, output_duration, offsets, enabled}.
    Hard joins use concat; soft/hold use xfade.
    join_styles: optional per-join xfade names (length n-1); falls back to `transition`.
    """
    n = len(segment_durs)
    if n == 0:
        raise PolicyError("need at least one segment")
    tl = segment_timeline(
        segment_durs,
        transition_sec,
        join_intents=join_intents,
        join_use_ts=join_use_ts,
    )
    if not tl["enabled"]:
        return {
            "filter_complex": "",
            "output_label": "0:v",
            "output_duration": tl["output_duration"],
            "offsets": [],
            "starts": tl["starts"],
            "use_ts": tl["use_ts"],
            "join_intents": tl.get("join_intents"),
            "enabled": False,
            "n_inputs": n,
            "method": "hard_concat",
        }

    n_joins = n - 1
    default_style = normalize_xfade_style(transition)
    if join_styles is None:
        styles = [default_style] * n_joins
    else:
        styles = normalize_transition_styles(join_styles, n_joins=n_joins, fallback=default_style)

    # Normalize each stream first for consistent format
    parts: list[str] = []
    for i in range(n):
        parts.append(f"[{i}:v]settb=AVTB,fps=30,format=yuv420p[v{i}]")

    offsets: list[float] = list(tl["starts"][1:])
    prev = "v0"
    methods: list[str] = []
    used_styles: list[str] = []
    # After each hard concat, reset PTS so subsequent xfade offsets stay valid.
    for i in range(1, n):
        use_t = float(tl["use_ts"][i - 1])
        offset = float(tl["starts"][i])
        out = f"vx{i}"
        if use_t <= 1e-6:
            parts.append(
                f"[{prev}][v{i}]concat=n=2:v=1:a=0,setpts=PTS-STARTPTS,settb=AVTB,fps=30,format=yuv420p[{out}]"
            )
            methods.append("hard")
            used_styles.append("hard")
        else:
            style = styles[i - 1] if i - 1 < len(styles) else default_style
            # xfade offset is on the progressive output clock from segment_timeline
            parts.append(
                f"[{prev}][v{i}]xfade=transition={style}:duration={use_t:.3f}:offset={offset:.3f},"
                f"setpts=PTS-STARTPTS,settb=AVTB,fps=30,format=yuv420p[{out}]"
            )
            methods.append("soft")
            used_styles.append(style)
        prev = out

    return {
        "filter_complex": ";".join(parts),
        "output_label": prev,
        "output_duration": tl["output_duration"],
        "offsets": offsets,
        "starts": tl["starts"],
        "use_ts": tl["use_ts"],
        "join_intents": tl.get("join_intents"),
        "join_methods": methods,
        "join_styles": used_styles,
        "enabled": True,
        "n_inputs": n,
        "transition": default_style,
        "transition_sec": float(transition_sec),
        "method": "mixed"
        if "hard" in methods and "soft" in methods
        else ("xfade" if "soft" in methods else "hard_concat"),
    }


def build_acrossfade_filter_graph(
    n_inputs: int,
    *,
    transition_sec: float = DEFAULT_TRANSITION_SEC,
    segment_durs: list[float] | None = None,
    join_intents: list[str] | None = None,
    join_use_ts: list[float] | None = None,
) -> dict[str, Any]:
    """Audio counterpart of xfade: chain acrossfade / hard concat per join."""
    if n_inputs <= 0:
        raise PolicyError("need at least one audio input")
    if segment_durs is not None and len(segment_durs) != n_inputs:
        raise PolicyError("segment_durs length must match n_inputs")

    if segment_durs is not None:
        tl = segment_timeline(
            segment_durs,
            transition_sec,
            join_intents=join_intents,
            join_use_ts=join_use_ts,
        )
        use_ts = [float(u) for u in tl["use_ts"]]
        starts = list(tl["starts"])
        out_dur = tl["output_duration"]
        enabled = tl["enabled"]
    else:
        if n_inputs == 1 or transition_sec <= 0:
            return {
                "filter_complex": "",
                "output_label": "0:a",
                "enabled": False,
                "n_inputs": n_inputs,
                "use_ts": [],
                "starts": [0.0] * n_inputs if n_inputs else [],
            }
        use_ts = [float(transition_sec)] * (n_inputs - 1)
        starts = []
        cursor = 0.0
        for i in range(n_inputs):
            starts.append(cursor)
            if i + 1 < n_inputs:
                cursor = cursor + 1.0
        out_dur = None
        enabled = True

    if n_inputs == 1 or not enabled:
        return {
            "filter_complex": "",
            "output_label": "0:a",
            "enabled": False,
            "n_inputs": n_inputs,
            "use_ts": use_ts,
            "starts": starts,
            "output_duration": out_dur,
        }

    parts: list[str] = []
    for i in range(n_inputs):
        parts.append(
            f"[{i}:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[a{i}]"
        )
    prev = "a0"
    for i in range(1, n_inputs):
        out = f"ax{i}"
        use_t = use_ts[i - 1]
        if use_t <= 1e-6:
            parts.append(f"[{prev}][a{i}]concat=n=2:v=0:a=1[{out}]")
        else:
            parts.append(f"[{prev}][a{i}]acrossfade=d={use_t:.3f}:c1=tri:c2=tri[{out}]")
        prev = out
    return {
        "filter_complex": ";".join(parts),
        "output_label": prev,
        "enabled": True,
        "n_inputs": n_inputs,
        "transition_sec": float(transition_sec),
        "use_ts": use_ts,
        "starts": starts,
        "output_duration": out_dur,
        "join_intents": join_intents,
    }

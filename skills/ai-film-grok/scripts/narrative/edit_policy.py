#!/usr/bin/env python3
"""Pure edit policies for stretch, transitions, and shot motion language.

Separated from ffmpeg I/O so unit tests can assert product rules without reimplementing them.
"""

from __future__ import annotations

import math
import re
from typing import Any

# Video fit-to-VO — prefer gentle speed over harsh freezes; avoid short-form double-play
MAX_SPEEDUP = 1.12
MIN_SPEED = 0.88
# P0 · 2026-07-23: was 1.15 — I2V 6s→7–8s plate triggered stream_loop (= “跑两遍”)
# Only allow loop when target truly needs multi-cycle (e.g. long VO chapter bed).
LOOP_STRETCH_RATIO = 1.55
# P0 · 2026-08-04 γ: tighten freeze — long tpad clone reads as still/PPT pad
MAX_FREEZE_PAD_SEC = 0.15  # hard cap; prefer clamp plate / re-I2V over freeze mush
# When loop is forbidden (hook/action), keep freeze micro — was 0.40
MAX_FREEZE_PAD_NO_LOOP_SEC = 0.20
# Drive beats default cut_on=mid_motion (kinetic cut, not settle-hold)
DRIVE_CUT_FUNCTIONS = frozenset({"hook", "approach", "action", "climax", "impact", "peak"})
# Beats that must never stream_loop (product rule; mirrored in film_spec)
# P0 · 2026-07-23: expand — short-form I2V almost never wants a full replay.
NO_LOOP_DRAMATIC_FUNCTIONS = frozenset(
    {
        "hook",
        "action",
        "approach",
        "bridge",
        "sensory",
        "reaction",
        "afterglow",
    }
)
# Mild overshoot where we clamp target to one play (+ micro hold) instead of looping
SHORTFORM_NO_DOUBLE_RATIO = 1.50
# Typical Grok I2V plate length — never full-replay these unless author forces loop bed
SHORTFORM_SRC_MAX_SEC = 7.5
# When forbid_loop cannot cover the target, clamp is allowed for mild shortfall
# (agent can pad VO). Below this ratio of target, raise PolicyError instead —
# a 6s plate clamped to ~7s for a 14s target is a silently broken clip.
FORBID_LOOP_SEVERE_SHORTFALL_RATIO = 0.70

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


# ---------------------------------------------------------------------------
# Character stance / multi-POV (角色立场 · 2026-07-20)
# Whose eyes is this shot? Who has power? Cutting across stances elevates cinema.
# Full grammar: references/character-stance.md
# ---------------------------------------------------------------------------
VIEWPOINTS = frozenset(
    {
        "objective",  # neutral observer
        "subjective_pov",  # camera = character eyes
        "ots",  # over-the-shoulder favoring focal
        "reverse",  # reverse angle / shot-reverse-shot answer
        "reaction_to",  # face reacting to off-screen or partner action
        "dual",  # both bodies in frame (two-shot)
        "insert_object",  # object/detail, stance via ownership not face
    }
)
LOOK_AXES = frozenset({"left", "right", "center"})
# Common cast role keys (free string also ok; these get smart defaults)
FOCAL_ROLE_HINTS = frozenset(
    {"hero", "heroine", "partner", "other", "audience", "env", "crowd", "rival"}
)

_VIEWPOINT_ANGLE: dict[str, str] = {
    "objective": "eye level",
    "subjective_pov": "eye level",
    "ots": "slight over-shoulder eye level",
    "reverse": "eye level",
    "reaction_to": "eye level",
    "dual": "slight low",
    "insert_object": "high angle on detail",
}
_VIEWPOINT_SIZE: dict[str, str] = {
    "objective": "medium",
    "subjective_pov": "medium close",
    "ots": "medium",
    "reverse": "medium close",
    "reaction_to": "medium close",
    "dual": "medium full",
    "insert_object": "close-up",
}
_VIEWPOINT_FRAMING_HINT: dict[str, str] = {
    "objective": "balanced observer framing, full head headroom",
    "subjective_pov": "subjective POV frame as if through character eyes, no face of viewer",
    "ots": "over-shoulder favoring focal character, partner edge in frame",
    "reverse": "reverse angle answer shot, opposite look axis",
    "reaction_to": "reaction face priority, eyes readable, full head headroom",
    "dual": "two-shot both adult bodies readable, space between",
    "insert_object": "detail insert owned by focal, shallow DOF",
}


def normalize_viewpoint(value: object, *, field: str = "viewpoint") -> str:
    if not isinstance(value, str) or not value.strip():
        raise PolicyError(f"{field} must be one of {sorted(VIEWPOINTS)}")
    v = value.strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "obj": "objective",
        "neutral": "objective",
        "pov": "subjective_pov",
        "subjective": "subjective_pov",
        "first_person": "subjective_pov",
        "over_shoulder": "ots",
        "over_the_shoulder": "ots",
        "srs": "reverse",
        "shot_reverse": "reverse",
        "reverse_shot": "reverse",
        "reaction": "reaction_to",
        "react": "reaction_to",
        "two_shot": "dual",
        "twoshot": "dual",
        "insert": "insert_object",
        "object": "insert_object",
        "ecu_object": "insert_object",
    }
    v = aliases.get(v, v)
    if v not in VIEWPOINTS:
        raise PolicyError(f"{field} must be one of {sorted(VIEWPOINTS)}; got {value!r}")
    return v


def normalize_look_axis(value: object, *, field: str = "look_axis") -> str:
    if not isinstance(value, str) or not value.strip():
        raise PolicyError(f"{field} must be one of {sorted(LOOK_AXES)}")
    a = value.strip().lower()
    aliases = {"l": "left", "r": "right", "c": "center", "mid": "center"}
    a = aliases.get(a, a)
    if a not in LOOK_AXES:
        raise PolicyError(f"{field} must be one of {sorted(LOOK_AXES)}; got {value!r}")
    return a


def normalize_focal_character(value: object | None) -> str:
    """Return cleaned focal id/role; empty → hero default for storyteller."""
    if value is None:
        return "hero"
    if not isinstance(value, str):
        return "hero"
    s = value.strip().lower().replace(" ", "_")
    return s or "hero"


def suggest_focal_character(
    dramatic_function: str,
    *,
    previous_focal: str | None = None,
    cast_ids: list[str] | None = None,
    shot_index: int = 0,
) -> str:
    """Pick whose stance the shot serves (storyteller default hero-led)."""
    fn = (dramatic_function or "bridge").strip().lower()
    prev = normalize_focal_character(previous_focal) if previous_focal else ""
    cast = [normalize_focal_character(c) for c in (cast_ids or []) if c]
    partner = next((c for c in cast if c not in {"hero", "heroine", "env", "audience"}), None)
    if not partner and cast:
        partner = next((c for c in cast if c != "hero"), cast[0])
    partner = partner or "partner"

    # Beat → default empathy owner
    if fn == "reaction":
        # reaction usually the one *receiving* pressure — often hero, or switch
        if prev and prev != "hero":
            return "hero"
        return partner if shot_index % 2 else "hero"
    if fn == "sensory":
        return prev or "hero"  # body detail stays with current owner
    if fn in {"action", "approach"}:
        return "hero"  # agency with protagonist unless cast forces otherwise
    if fn == "hook":
        return "hero"
    if fn == "afterglow":
        return "hero"
    if fn == "bridge":
        return prev or "env"
    return prev or "hero"


def suggest_viewpoint(
    dramatic_function: str,
    *,
    focal: str | None = None,
    previous_viewpoints: list[str] | None = None,
    previous_viewpoint: str | None = None,
    previous_focal: str | None = None,
    shot_index: int = 0,
) -> str:
    """Pick viewpoint grammar for multi-stance cinema (not always objective)."""
    fn = (dramatic_function or "bridge").strip().lower()
    foc = normalize_focal_character(focal)

    if previous_viewpoints and len(previous_viewpoints) > 0:
        prev_v = previous_viewpoints[-1].strip().lower()
    else:
        prev_v = (previous_viewpoint or "").strip().lower()

    prev_f = normalize_focal_character(previous_focal) if previous_focal else ""
    focal_shifted = bool(prev_f and foc and prev_f != foc)

    # Anti-flat optimization (Lookahead check)
    if previous_viewpoints and len(previous_viewpoints) >= 2:
        if previous_viewpoints[-1] == "objective" and previous_viewpoints[-2] == "objective":
            # Force break out of objective soup
            if fn in {"action", "approach"}:
                return "ots"
            return "reaction_to" if fn == "reaction" else "ots"

    if fn == "sensory":
        return "insert_object"
    if fn == "reaction":
        return "reaction_to"
    if focal_shifted and prev_v in {"ots", "objective", "dual", "reverse"}:
        return "reverse"  # answer the other character
    if fn == "approach" and shot_index > 0:
        return "ots" if prev_v != "ots" else "dual"
    if fn == "action":
        # agency: mostly objective/ots; occasional subjective for immersion
        if shot_index % 4 == 3:
            return "subjective_pov"
        return "ots" if prev_v == "objective" else "objective"
    if fn == "hook":
        return "objective"
    if fn == "afterglow":
        return "dual" if prev_v != "dual" else "reaction_to"
    if fn == "bridge":
        return "objective"
    # default: avoid flat objective soup
    if prev_v == "objective":
        return "ots"
    return "objective"


def suggest_look_axis(
    viewpoint: str,
    *,
    previous_look: str | None = None,
) -> str:
    """180° screen direction: reverse flips left/right."""
    v = (viewpoint or "objective").strip().lower()
    prev = (previous_look or "").strip().lower()
    if v == "reverse" and prev in {"left", "right"}:
        return "right" if prev == "left" else "left"
    if v in {"ots", "reaction_to", "subjective_pov"}:
        if prev == "left":
            return "left"  # keep axis until reverse
        if prev == "right":
            return "right"
        return "left"
    if v == "insert_object":
        return prev if prev in LOOK_AXES else "center"
    return "center"


def viewpoint_coverage_hints(viewpoint: str) -> dict[str, str]:
    """Angle / size / framing hints from viewpoint (author values still win)."""
    v = normalize_viewpoint(viewpoint) if viewpoint else "objective"
    return {
        "angle": _VIEWPOINT_ANGLE.get(v, "eye level"),
        "shot_size": _VIEWPOINT_SIZE.get(v, "medium"),
        "framing_hint": _VIEWPOINT_FRAMING_HINT.get(
            v, "vertical 9:16 balanced framing, full head headroom"
        ),
        "viewpoint": v,
    }


def lint_character_stance(
    shots: list[dict[str, Any]],
) -> dict[str, Any]:
    """Soft lint: flat objective, no focal variety, reverse without partner shift."""
    issues: list[dict[str, Any]] = []
    codes: list[str] = []
    if len(shots) < 2:
        return {"ok": True, "codes": [], "issues": [], "warning_count": 0}

    viewpoints: list[str] = []
    focals: list[str] = []
    for i, sh in enumerate(shots):
        if not isinstance(sh, dict):
            continue
        dsl = sh.get("dsl") if isinstance(sh.get("dsl"), dict) else {}
        vp = str(dsl.get("viewpoint") or sh.get("viewpoint") or "").strip().lower()
        foc = normalize_focal_character(dsl.get("focal_character") or sh.get("focal_character"))
        viewpoints.append(vp or "objective")
        focals.append(foc)

    non_obj = [v for v in viewpoints if v and v != "objective"]
    if len(shots) >= 4 and len(non_obj) == 0:
        codes.append("VIEWPOINT_FLAT")
        issues.append(
            {
                "code": "VIEWPOINT_FLAT",
                "message": "all shots objective — multi-stance cinema wants ots/reverse/reaction/pov",
            }
        )
    unique_focal = {f for f in focals if f and f not in {"env", "audience"}}
    if len(shots) >= 6 and len(unique_focal) <= 1:
        # storyteller single-lead ok, but soft warn if reaction never switches empathy
        reaction_idx = [
            i
            for i, sh in enumerate(shots)
            if isinstance(sh, dict) and str(sh.get("dramatic_function") or "").lower() == "reaction"
        ]
        if reaction_idx and all(focals[i] == focals[0] for i in reaction_idx):
            codes.append("FOCAL_STANCE_FLAT")
            issues.append(
                {
                    "code": "FOCAL_STANCE_FLAT",
                    "message": (
                        "reaction beats never switch focal_character — "
                        "consider partner reaction for power/empathy flip"
                    ),
                }
            )
    # reverse without focal change is weak reverse
    for i in range(1, len(viewpoints)):
        if viewpoints[i] == "reverse" and focals[i] == focals[i - 1]:
            codes.append("REVERSE_WITHOUT_FOCAL_SHIFT")
            issues.append(
                {
                    "code": "REVERSE_WITHOUT_FOCAL_SHIFT",
                    "shot_index": i,
                    "message": "reverse viewpoint but same focal — prefer flip focal_character",
                }
            )
            break

    return {
        "ok": len(codes) == 0,
        "codes": codes,
        "issues": issues,
        "warning_count": len(issues),
        "viewpoint_set": sorted(set(viewpoints)),
        "focal_set": sorted(unique_focal),
    }


# Motion validation
FORBIDDEN_MOTION_PATTERNS = (
    re.compile(r"\bmouth\s+speaking\b", re.I),
    re.compile(r"\bspeaking\s+mouth\b", re.I),
    re.compile(r"\blip[\s-]?sync\b", re.I),
    re.compile(r"\btalking\s+to\s+camera\b", re.I),
    re.compile(r"\bdialogue\s+mouth\b", re.I),
)
# Require at least one camera/body/environment cue (not empty / not only punctuation)
MOTION_POSITIVE_HINTS = (
    "push",
    "pull",
    "pan",
    "tilt",
    "orbit",
    "dolly",
    "track",
    "handheld",
    "parallax",
    "blink",
    "breath",
    "lean",
    "hair",
    "wind",
    "water",
    "look",
    "turn",
    "walk",
    "float",
    "sway",
    "idle",
    "camera",
    "slow",
    "ripple",
    "drip",
    "fabric",
)


# PolicyError + coitus markers live in edit_policy_shared (cycle-free leaf).
from edit_policy_shared import (  # noqa: E402
    PolicyError,
)


def _loop_plan(
    src_dur: float,
    target: float,
    ratio: float,
    *,
    upgraded_from: str | None = None,
) -> dict[str, Any]:
    loops = max(0, int(math.ceil(target / src_dur + 0.05)) - 1)
    factor = min(MAX_SPEEDUP, max(1.0, min(ratio / max(loops + 1, 1), MAX_SPEEDUP)))
    plan: dict[str, Any] = {
        "mode": "loop",
        "factor": factor,
        "loops": loops,
        "freeze_sec": 0.0,
        "ratio": ratio,
        "src_dur": src_dur,
        "target": target,
    }
    if upgraded_from:
        plan["upgraded_from"] = upgraded_from
    return plan


def _setpts_pad_plan(
    src_dur: float,
    target: float,
    ratio: float,
    *,
    max_freeze: float,
    forbid_loop: bool,
) -> dict[str, Any]:
    """Stretch/pad without stream_loop (used for hook/action and mild ratios)."""
    if ratio < MIN_SPEED:
        factor = MIN_SPEED
    elif ratio > MAX_SPEEDUP:
        factor = MAX_SPEEDUP
    else:
        factor = ratio
    after = src_dur * factor
    pad = max(0.0, target - after)
    freeze = min(pad, max_freeze) if pad > 0.05 else 0.0
    # If VO still longer than plate+freeze, fail closed — agent must shorten nar / lengthen plate.
    covered = after + freeze
    if forbid_loop and target > covered + 0.05:
        raise PolicyError(
            f"forbid_loop stretch cannot cover target={target:.2f}s from src={src_dur:.2f}s "
            f"(max_freeze={max_freeze}s). Shorten VO or raise duration_sec / re-I2V at 10s."
        )
    mode = "setpts_pad" if freeze > 0 else "setpts"
    return {
        "mode": mode,
        "factor": factor,
        "loops": 0,
        "freeze_sec": freeze,
        "ratio": ratio,
        "src_dur": src_dur,
        "target": target,
        "forbid_loop": forbid_loop,
    }


def plan_stretch(
    src_dur: float,
    target: float,
    *,
    forbid_loop: bool = False,
    dramatic_function: str | None = None,
    allow_shortform_clamp: bool = True,
) -> dict[str, Any]:
    """Decide how to fit a silent clip to a VO-driven target duration.

    Returns a plan dict:
      mode: "loop" | "setpts" | "setpts_pad"
      factor: playback setpts factor
      loops: stream_loop count (0 = no loop)
      freeze_sec: tpad clone seconds (capped)
      ratio: target/src
      target_clamped: optional new target when shortform clamp applied

    Product rules:
      - 2026-07-16 Kei: hook/action never stream_loop
      - 2026-07-23 E-virus: short I2V plates must not stream_loop for mild overshoot
        (6s clip → 7–8s slot = “跑两遍”); clamp to one play + micro hold instead.
    """
    if src_dur <= 0:
        raise PolicyError("src_dur must be > 0")
    if target <= 0:
        raise PolicyError("target must be > 0")
    beat = (dramatic_function or "").strip().lower()
    if beat in NO_LOOP_DRAMATIC_FUNCTIONS:
        forbid_loop = True
    # P0 · 2026-07-23: typical short I2V plates (~4–7.5s) stream_loop reads
    # as “跑两遍”; very short source clips still need looping to reach a shot.
    if 4.0 <= src_dur <= SHORTFORM_SRC_MAX_SEC:
        forbid_loop = True
    ratio = target / src_dur
    max_freeze = MAX_FREEZE_PAD_NO_LOOP_SEC if forbid_loop else MAX_FREEZE_PAD_SEC

    # Short-form anti-double: mild overshoot → clamp target to one natural play
    if (
        allow_shortform_clamp
        and ratio > 1.0
        and ratio <= SHORTFORM_NO_DOUBLE_RATIO
        and (forbid_loop or ratio <= LOOP_STRETCH_RATIO)
    ):
        # One play at ≤ MAX_SPEEDUP, then ≤ max_freeze hold — never stream_loop
        natural = src_dur * MAX_SPEEDUP + max_freeze
        clamped = min(target, max(src_dur, natural))
        if clamped + 1e-3 < target:
            plan = _setpts_pad_plan(
                src_dur,
                clamped,
                clamped / src_dur,
                max_freeze=max_freeze,
                forbid_loop=True,
            )
            plan["target_clamped"] = clamped
            plan["target_requested"] = target
            plan["clamp_reason"] = "shortform_no_double_play"
            return plan

    if forbid_loop:
        # If still cannot cover, clamp rather than raise (agent can still pad VO)
        try:
            return _setpts_pad_plan(src_dur, target, ratio, max_freeze=max_freeze, forbid_loop=True)
        except PolicyError:
            natural = src_dur * MAX_SPEEDUP + max_freeze
            # Severe shortfall: clamp would silently produce a clip far shorter
            # than the VO (e.g. 6s plate → 7s natural for a 14s target).
            # Fail closed so the agent shortens nar / re-I2Vs at a longer duration.
            if natural < target * FORBID_LOOP_SEVERE_SHORTFALL_RATIO:
                raise
            plan = _setpts_pad_plan(
                src_dur,
                natural,
                natural / src_dur,
                max_freeze=max_freeze,
                forbid_loop=True,
            )
            plan["target_clamped"] = natural
            plan["target_requested"] = target
            plan["clamp_reason"] = "forbid_loop_clamp"
            return plan

    if ratio > LOOP_STRETCH_RATIO:
        return _loop_plan(src_dur, target, ratio)

    if ratio < MIN_SPEED:
        factor = MIN_SPEED
    elif ratio > MAX_SPEEDUP:
        factor = MAX_SPEEDUP
    else:
        factor = ratio

    after = src_dur * factor
    pad = max(0.0, target - after)
    # Mild pad only — do not upgrade to loop for shortform double-play
    extension = max(0.0, target - src_dur)
    if pad > MAX_FREEZE_PAD_SEC or (extension > 0.5 and pad > extension * 0.45):
        if ratio > LOOP_STRETCH_RATIO:
            return _loop_plan(src_dur, target, ratio, upgraded_from="setpts_pad")
        # Clamp instead of loop for mild cases
        natural = after + MAX_FREEZE_PAD_SEC
        plan = _setpts_pad_plan(
            src_dur,
            min(target, natural),
            min(target, natural) / src_dur,
            max_freeze=MAX_FREEZE_PAD_SEC,
            forbid_loop=True,
        )
        plan["target_clamped"] = plan["target"]
        plan["target_requested"] = target
        plan["clamp_reason"] = "prefer_clamp_over_loop"
        return plan

    freeze = min(pad, MAX_FREEZE_PAD_SEC) if pad > 0.05 else 0.0
    mode = "setpts_pad" if freeze > 0 else "setpts"
    return {
        "mode": mode,
        "factor": factor,
        "loops": 0,
        "freeze_sec": freeze,
        "ratio": ratio,
        "src_dur": src_dur,
        "target": target,
        "forbid_loop": False,
    }


def default_visual_fit(spec: dict[str, Any] | None) -> str:
    """Film-level visual_fit default (Wave γ · anti-PPT).

    dialogue_drama / voice_coupled / punchy → ``vo`` (plate follows speech length).
    Otherwise ``slot`` (duration_sec locks plate; VO atempo).
    """
    spec = spec if isinstance(spec, dict) else {}
    explicit = str(spec.get("visual_fit") or "").strip().lower()
    if explicit in {"vo", "slot"}:
        return explicit
    vo_mode = str(spec.get("vo_mode") or "").strip().lower()
    if vo_mode == "dialogue_drama":
        return "vo"
    es = spec.get("edit_strategy") if isinstance(spec.get("edit_strategy"), dict) else {}
    es_mode = str(es.get("mode") or "").strip().lower()
    if es_mode in {"voice_coupled", "punchy"}:
        return "vo"
    # Genre pack: dialogue-first product
    genre = str(spec.get("genre") or "").strip().lower()
    if genre in {"dialogue", "dialogue_drama", "adult"} and vo_mode in {
        "character",
        "hybrid",
        "dialogue_drama",
        "",
    }:
        # adult without explicit mode still often dialogue — prefer vo when spoken heavy
        if vo_mode == "dialogue_drama" or genre == "dialogue_drama":
            return "vo"
    return "slot"


def shot_has_spoken_dialogue(shot: dict[str, Any] | None) -> bool:
    if not isinstance(shot, dict):
        return False
    if str(shot.get("spoken_text") or "").strip():
        return True
    sm = str(shot.get("screen_mode") or "").strip().lower()
    if sm in {"on_camera", "off_camera"}:
        return True
    for cue in shot.get("audio_cues") or []:
        if not isinstance(cue, dict):
            continue
        kind = str(cue.get("kind") or "voice").strip().lower()
        if kind not in {"voice", "dialogue", ""}:
            continue
        lt = str(cue.get("line_type") or "dialogue").strip().lower()
        if lt == "narration":
            continue
        line = str(cue.get("spoken_text") or cue.get("text") or "").strip()
        if line:
            return True
    return False


def resolve_shot_visual_fit(
    spec: dict[str, Any] | None,
    shot: dict[str, Any] | None,
) -> str:
    """Per-shot plate fit: vo | slot (Wave γ).

    Priority: shot.visual_fit → mid_motion cut_on → spoken dialogue → film default.
    """
    shot = shot if isinstance(shot, dict) else {}
    shot_fit = str(shot.get("visual_fit") or "").strip().lower()
    if shot_fit in {"vo", "slot"}:
        return shot_fit
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    cut_on = str(dsl.get("cut_on") or "").strip().lower()
    if cut_on in {"mid_motion", "mid-action", "action", "mid-motion"}:
        return "vo"
    if shot_has_spoken_dialogue(shot):
        return "vo"
    return default_visual_fit(spec)


def default_cut_on_for_shot(shot: dict[str, Any] | None) -> str | None:
    """Suggest cut_on for drive beats (mid_motion) when author left blank."""
    if not isinstance(shot, dict):
        return None
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    existing = str(dsl.get("cut_on") or "").strip().lower()
    if existing:
        return existing
    fn = str(shot.get("dramatic_function") or "").strip().lower()
    if fn in DRIVE_CUT_FUNCTIONS:
        return "mid_motion"
    heat = str(shot.get("heat_phase") or "").strip().lower()
    if heat in {"act", "climax"}:
        return "mid_motion"
    return None


def apply_shot_edit_rhythm_defaults(shot: dict[str, Any]) -> dict[str, Any]:
    """Fill missing dsl.cut_on for drive shots (mutates shot). Returns notes."""
    notes: dict[str, Any] = {"cut_on_applied": False}
    if not isinstance(shot, dict):
        return notes
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else None
    if dsl is None:
        return notes
    suggested = default_cut_on_for_shot(shot)
    existing = str(dsl.get("cut_on") or "").strip()
    if not existing and suggested:
        dsl["cut_on"] = suggested
        shot["dsl"] = dsl
        notes["cut_on_applied"] = True
        notes["cut_on"] = suggested
    return notes


def apply_film_edit_rhythm_defaults(spec: dict[str, Any]) -> dict[str, Any]:
    """Film-level visual_fit + per-shot cut_on defaults (mutates spec)."""
    applied: list[str] = []
    if not isinstance(spec, dict):
        return {"ok": False, "applied": []}
    if not str(spec.get("visual_fit") or "").strip():
        fit = default_visual_fit(spec)
        # Only write when dialogue_drama / voice_coupled would choose vo,
        # or leave unset for slot default at render time.
        if fit == "vo":
            spec["visual_fit"] = "vo"
            applied.append("visual_fit=vo")
    shots_touched = 0
    for scene in spec.get("scenes") or []:
        if not isinstance(scene, dict):
            continue
        for shot in scene.get("shots") or []:
            if not isinstance(shot, dict):
                continue
            n = apply_shot_edit_rhythm_defaults(shot)
            if n.get("cut_on_applied"):
                shots_touched += 1
    if shots_touched:
        applied.append(f"cut_on_mid_motion×{shots_touched}")
    report = {
        "ok": True,
        "applied": applied,
        "visual_fit": str(spec.get("visual_fit") or default_visual_fit(spec)),
        "cut_on_drive_default": "mid_motion",
        "max_freeze_pad_sec": MAX_FREEZE_PAD_SEC,
        "max_freeze_no_loop_sec": MAX_FREEZE_PAD_NO_LOOP_SEC,
        "note": (
            "Wave γ: dialogue_drama default visual_fit=vo; drive cut_on=mid_motion; "
            "freeze pad ≤0.15s (no long still pad)"
        ),
    }
    spec["_edit_rhythm"] = report
    return report


def lint_equal_duration_ppt(
    shots: list[dict[str, Any]],
    *,
    visual_fit: str = "slot",
    equal_tol: float = 0.05,
    min_shots: int = 4,
) -> dict[str, Any]:
    """Flag equal-length slots that read as PPT when not VO-fit."""
    issues: list[dict[str, Any]] = []
    if visual_fit == "vo":
        return {"ok": True, "issues": [], "codes": []}
    durs = []
    for s in shots:
        if not isinstance(s, dict):
            continue
        try:
            durs.append(float(s.get("duration_sec") or 0))
        except (TypeError, ValueError):
            continue
    if len(durs) < min_shots:
        return {"ok": True, "issues": [], "codes": []}
    # majority equal (~6s classic pad)
    from collections import Counter

    rounded = [round(d, 1) for d in durs if d > 0]
    if not rounded:
        return {"ok": True, "issues": [], "codes": []}
    common, count = Counter(rounded).most_common(1)[0]
    if count >= min_shots and count / len(rounded) >= 0.75 and abs(common - 6.0) < 0.6:
        issues.append(
            {
                "code": "EQUAL_SLOT_PPT_RISK",
                "message": (
                    f"{count}/{len(rounded)} shots share ~{common}s duration — "
                    "reads as equal-length PPT; set visual_fit=vo for dialogue "
                    "or vary duration_sec / re-I2V length"
                ),
            }
        )
    return {
        "ok": not issues,
        "issues": issues,
        "codes": [i["code"] for i in issues],
        "common_duration": common if rounded else None,
        "equal_count": count if rounded else 0,
    }


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
    foc = [normalize_focal_character(x) for x in (focals or [])]
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


# Camera axis menu (运镜主轴) — rotate across shots; inject into motion when missing.
# lessons-2026-07-20-transition-motion-v2 / 男娘咖啡厅
CAMERA_AXES = (
    "dolly_in",  # push-in / dolly toward subject
    "pan_with",  # horizontal pan-with-subject
    "locked",  # static locked-off; only body/prop moves
    "ecu_hold",  # tight hold / micro-tremble, no push-in
    "low_lean",  # low angle lean-in then stop
    "pull_back",  # gentle pull-back then hold
)
CAMERA_AXIS_MOTION_PHRASE: dict[str, str] = {
    "dolly_in": "continuous slow dolly-in on subject",
    "pan_with": "horizontal pan-with-subject, no push-in",
    "locked": "camera static locked-off, only body or prop moves",
    "ecu_hold": "tight hold, micro-tremble only, no push-in",
    "low_lean": "low angle lean-in then stop",
    "pull_back": "gentle pull-back then hold",
}
# Tokens that already mark a camera axis in author motion text
_CAMERA_AXIS_HINTS: dict[str, tuple[str, ...]] = {
    "dolly_in": ("dolly", "push-in", "push in", "track in", "creep in"),
    "pan_with": ("pan-with", "pan with", "horizontal pan", "track left", "track right"),
    "locked": ("locked-off", "locked off", "camera static", "static locked", "tripod lock"),
    "ecu_hold": ("ecu", "extreme cu", "tight hold", "micro-tremble", "no push-in"),
    "low_lean": ("low angle", "lean-in", "lean in", "low lean"),
    "pull_back": ("pull-back", "pull back", "dolly out", "zoom out gently"),
}


def infer_camera_axis(motion: str | None) -> str | None:
    """Detect camera axis from motion text; None if none recognized."""
    low = (motion or "").strip().lower()
    if not low:
        return None
    for axis, hints in _CAMERA_AXIS_HINTS.items():
        if any(h in low for h in hints):
            return axis
    return None


def suggest_camera_axis(
    dramatic_function: str,
    *,
    previous_axes: list[str] | None = None,
    shot_index: int = 0,
) -> str:
    """Pick a camera axis for this beat, avoiding the last 1–2 axes when possible."""
    fn = (dramatic_function or "bridge").strip().lower()
    preferred: dict[str, tuple[str, ...]] = {
        "hook": ("dolly_in", "low_lean", "pan_with"),
        "approach": ("pan_with", "dolly_in", "locked"),
        "sensory": ("ecu_hold", "dolly_in", "locked"),
        "reaction": ("locked", "ecu_hold", "pan_with"),
        "action": ("locked", "low_lean", "pan_with"),
        "afterglow": ("pull_back", "locked", "dolly_in"),
        "bridge": ("pan_with", "locked", "pull_back"),
    }
    candidates = list(preferred.get(fn, CAMERA_AXES))
    # append rest of menu for fallback
    for ax in CAMERA_AXES:
        if ax not in candidates:
            candidates.append(ax)
    prev = [a for a in (previous_axes or []) if a]
    recent = set(prev[-2:]) if prev else set()
    for ax in candidates:
        if ax not in recent:
            return ax
    return candidates[shot_index % len(candidates)]


def _motion_has_camera_language(motion: str | None) -> bool:
    """True if author already named a camera/body-camera cue (orbit/pan/push/…)."""
    low = (motion or "").strip().lower()
    if not low:
        return False
    if infer_camera_axis(low):
        return True
    cues = (
        "orbit",
        "tilt",
        "track",
        "handheld",
        "parallax",
        "dolly",
        "push",
        "pan",
        "camera",
        "static",
        "locked",
        "creep",
        "glide",
    )
    return any(c in low for c in cues)


def _is_mouth_primary_only(motion: str | None) -> bool:
    """Mouth-speaking without body/camera cues — must stay rejectable by validate_motion."""
    lowered = (motion or "").strip().lower()
    if not lowered:
        return False
    for pat in FORBIDDEN_MOTION_PATTERNS:
        if pat.search(lowered) and not any(
            h in lowered for h in ("idle", "blink", "breath", "camera", "push", "pan")
        ):
            return True
    return False


def inject_camera_axis_phrase(motion: str, axis: str) -> str:
    """Ensure motion mentions the chosen camera axis (append if missing)."""
    text = (motion or "").strip()
    if _is_mouth_primary_only(text):
        return text  # do not launder forbidden mouth-primary motion
    phrase = CAMERA_AXIS_MOTION_PHRASE.get(axis, CAMERA_AXIS_MOTION_PHRASE["dolly_in"])
    if infer_camera_axis(text) == axis:
        return text
    if _motion_has_camera_language(text):
        return text  # author already chose a camera move (e.g. orbit)
    if not text:
        return f"{phrase}, idle not speaking"
    if "idle not speaking" in text.lower():
        base = text
        idx = base.lower().rfind("idle not speaking")
        if idx >= 0:
            base = base[:idx].rstrip(" ,;")
        return f"{base}, {phrase}, idle not speaking"
    return f"{text}, {phrase}, idle not speaking"


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


def validate_motion(motion: object, *, field: str = "dsl.motion") -> str:
    """Require non-empty motion language; reject mouth-speaking-primary patterns."""
    if not isinstance(motion, str) or not motion.strip():
        raise PolicyError(f"{field} is required (camera + body/idle beat, not empty)")
    text = motion.strip()
    if len(text) < 4:
        raise PolicyError(f"{field} too short — describe camera and body action")
    lowered = text.lower()
    for pat in FORBIDDEN_MOTION_PATTERNS:
        if pat.search(lowered):
            # Allow if also has idle/camera language and is hybrid
            if not any(h in lowered for h in ("idle", "blink", "breath", "camera", "push", "pan")):
                raise PolicyError(
                    f"{field} rejects mouth-speaking as primary motion; "
                    "use idle/camera body language (storyteller default)"
                )
            # still reject pure "mouth speaking" alone
            if re.fullmatch(r"[\s,;:-]*mouth\s+speaking[\s,;:-]*", lowered):
                raise PolicyError(f"{field} cannot be only mouth speaking")
    if not any(h in lowered for h in MOTION_POSITIVE_HINTS):
        raise PolicyError(
            f"{field} should include camera or body cues "
            f"(e.g. push-in, blink, breath, lean, hair, idle) — got: {text[:80]!r}"
        )
    return text


def i2v_motion_templates() -> dict[str, str]:
    """Agent-facing motion snippets — continuous, one-axis motion (storyteller-safe).

    Primary body/prop verb first for hook/approach/action; micro fillers last.
    Avoid multi-action thrash that warps faces. See lessons-2026-07-17-vo-motion-link.
    Adult coitus keys (union/rhythm/…) are for heat_phase=act|climax — not soft defaults.
    """
    return {
        "idle_closeup": (
            "continuous slow push-in, soft blink, subtle breath, hair micro-sway, "
            "closed lips, idle not speaking"
        ),
        "idle_medium": (
            "gentle continuous pan, fabric drift, ambient light flicker, soft blink, "
            "idle not speaking"
        ),
        "approach": (
            "slow step closer, body lean toward camera, smooth dolly-in, "
            "then breath and hair sway, idle not speaking"
        ),
        "environment": (
            "parallax drift, water or wind continuous motion, soft handheld glide, "
            "subject mostly still, idle not speaking"
        ),
        "afterglow": (
            "hold then micro push-in, soft smile micro-move, rim light flicker, "
            "hair wind, residual-tremor breath, idle not speaking"
        ),
        "hook": (
            "one establishing body or prop action (hand on latch / door close / turn), "
            "establishing smooth push-in, then ambient motion, soft blink, breath, "
            "idle not speaking"
        ),
        "sensory": (
            "extreme slow continuous push-in, micro breath, hair sway, "
            "shallow focus drift, idle not speaking"
        ),
        "reaction": (
            "slow push-in on eyes, subtle flinch, blush micro-move, breath hitch, idle not speaking"
        ),
        "action": (
            "single readable body action first (unhook, belt pull, lean-in, hand extend), "
            "smooth camera track with subject, fabric move, then soft blink, idle not speaking"
        ),
        "bridge": (
            "gentle continuous pan, light flicker, transitional look, soft handheld, "
            "idle not speaking"
        ),
        # --- Adult coitus grammar motion (heat act/climax · 2026-07-22) ---
        "undress_slide": (
            "primary: straps slide off shoulders, dress/armor peels down torso once, "
            "bare skin expands, Keep first-frame clothing direction only more undressed, "
            "smooth track with hands, breath hitch, idle not speaking"
        ),
        "entry_pin": (
            "primary: pin partner to seat/bed, weight drop, pelvis aim, mount-settle start, "
            "low-angle lean-stop, fabric clutch, breath, idle not speaking"
        ),
        "union_settle": (
            "primary: straddle-seat hips settle into pelvis-lock, weight fully down once, "
            "thighs clamp, hair-pull anchor, body-weight grind, skin-to-skin friction, "
            "camera locked slight low, breath hitch, idle not speaking"
        ),
        "rhythm_hips": (
            "primary: hips-sink twice with grind-forward thrust-rhythm, pelvis readable, "
            "deep penetrating thrusts, locked camera or micro rock with body, "
            "clutch fabric, wet skin friction, breath, idle not speaking"
        ),
        "lock_clutch": (
            "primary: leg-wrap-waist lock, fingers clutch sheets/flesh, micro-tremor squeeze, "
            "ecu_hold on hands or hip line, body trembling, idle not speaking"
        ),
        "deep_thrust": (
            "primary: deep penetrating thrust, pelvis bottoming out repeatedly, "
            "skin-to-skin friction impact, heavy breath hitch, body-weight drive, "
            "locked low angle, idle not speaking"
        ),
        "internal_peak": (
            "primary: internal ejaculation peak, body overflow, trembling climax, "
            "bare skin contact, heavy pelvic thrust, wet vocalization, "
            "camera locked close, idle not speaking"
        ),
        "creampie_release": (
            "primary: creampie release, internal overflow, biological fluid leak, "
            "bare skin friction, residual throbbing, heavy breath, "
            "close-up on contact, idle not speaking"
        ),
        "finish_arch": (
            "primary: arch-finish spine curve, residual-tremor, wet eyes, body softens after peak, "
            "static hold then micro breath, idle not speaking"
        ),
        "hook_whisper": (
            "primary: lean to ear, residual afterglow hold, soft pull-back, "
            "whisper posture not speaking lips sealed, idle not speaking"
        ),
    }


# Coitus beat → preferred motion template key
COITUS_BEAT_MOTION_KEY: dict[str, str] = {
    "entry": "entry_pin",
    "union": "union_settle",
    "rhythm": "rhythm_hips",
    "lock": "lock_clutch",
    "finish": "finish_arch",
    "hook": "hook_whisper",
    "undress": "undress_slide",
    "deep_thrust": "deep_thrust",
    "internal_peak": "internal_peak",
    "creampie_release": "creampie_release",
}

# COITUS_* / PolicyError imported from edit_policy_shared above (re-exported).

# dramatic_function → default coverage (shot_size + motion + composition)
BEAT_COVERAGE_DEFAULTS: dict[str, dict[str, str]] = {
    "hook": {
        "shot_size": "medium full",
        "motion_key": "hook",
        "angle": "eye level",
        "framing": (
            "vertical 9:16 medium full waist-up, subject mid-frame with full head and both shoulders "
            "inside frame, ample headroom, safe framing no cropping, lead room toward gaze"
        ),
    },
    "approach": {
        "shot_size": "medium",
        "motion_key": "approach",
        "angle": "eye level",
        "framing": (
            "vertical 9:16 medium waist-up, eyes on upper third, full head visible, "
            "ample headroom, safe framing no cropping, space between bodies narrowing"
        ),
    },
    "sensory": {
        "shot_size": "close-up",
        "motion_key": "sensory",
        "angle": "eye level",
        "framing": (
            "vertical 9:16 close-up detail (eyes lips collarbone hands), shallow DOF, "
            "full head and both shoulders inside frame, ample headroom, safe framing no cropping"
        ),
    },
    "reaction": {
        "shot_size": "close-up",
        "motion_key": "reaction",
        "angle": "eye level",
        "framing": (
            "vertical 9:16 face-priority close-up, eyes sharp, full head visible, "
            "slight headroom, safe framing no cropping, emotion readable"
        ),
    },
    "action": {
        "shot_size": "medium full",
        "motion_key": "action",
        "angle": "slight low",
        "framing": (
            "vertical 9:16 body action readable, full head and limbs not cropped mid-joint, "
            "ample headroom, subject stays framed, stable screen direction"
        ),
    },
    "afterglow": {
        "shot_size": "medium",
        "motion_key": "afterglow",
        "angle": "eye level",
        "framing": (
            "vertical 9:16 residual intimacy medium, full head + headroom, "
            "safe framing no cropping, soft bokeh, hold composition after heat"
        ),
    },
    "bridge": {
        "shot_size": "medium",
        "motion_key": "bridge",
        "angle": "eye level",
        "framing": (
            "vertical 9:16 transitional medium, full head + headroom, "
            "safe framing no cropping, clear screen direction into next beat"
        ),
    },
}


def coverage_defaults_for_beat(dramatic_function: str) -> dict[str, str]:
    """Map beat role to default shot_size, angle, framing + motion (storyteller-safe)."""
    fn = (dramatic_function or "").strip().lower()
    if fn not in BEAT_COVERAGE_DEFAULTS:
        raise PolicyError(f"unknown dramatic_function for coverage defaults: {dramatic_function!r}")
    templates = i2v_motion_templates()
    row = BEAT_COVERAGE_DEFAULTS[fn]
    key = row["motion_key"]
    motion = templates.get(key) or templates["idle_medium"]
    return {
        "dramatic_function": fn,
        "shot_size": row["shot_size"],
        "angle": row.get("angle") or "eye level",
        "framing": row.get("framing") or "vertical 9:16 balanced framing",
        "motion_key": key,
        "motion": motion,
    }


def coverage_defaults_for_heat(
    dramatic_function: str,
    *,
    heat_phase: str | None = None,
    coitus_beat: str | None = None,
) -> dict[str, str]:
    """Coverage defaults with adult heat override for act/climax coitus beats."""
    base = coverage_defaults_for_beat(dramatic_function)
    ph = (heat_phase or "").strip().lower() or None
    cb = (coitus_beat or "").strip().lower() or None
    templates = i2v_motion_templates()
    if cb in COITUS_BEAT_MOTION_KEY:
        key = COITUS_BEAT_MOTION_KEY[cb]
        base["motion_key"] = key
        base["motion"] = templates.get(key) or base["motion"]
        if cb in {"union", "rhythm", "entry", "deep_thrust"}:
            base["shot_size"] = "medium"
            base["angle"] = "slight low"
            base["framing"] = (
                "vertical 9:16 pelvis and thighs readable, hips contact, "
                "full head + headroom, safe framing no cropping, weight down, skin-to-skin impact"
            )
        elif cb in {"lock", "finish", "internal_peak", "creampie_release"}:
            base["shot_size"] = "close-up"
            base["angle"] = "eye level"
            base["framing"] = (
                "vertical 9:16 close-up on peak reaction, bare skin contact visible, "
                "full head + headroom, safe framing no cropping, biological release readable"
            )
        elif cb == "undress":
            base["shot_size"] = "medium full"
            base["angle"] = "eye level"
        base["heat_phase"] = ph or ""
        base["coitus_beat"] = cb
        return base
    if ph in {"act", "climax"}:
        if cb == "deep_thrust":
            key = "deep_thrust"
        elif cb == "internal_peak":
            key = "internal_peak"
        elif cb == "creampie_release":
            key = "creampie_release"
        elif ph == "act":
            key = "rhythm_hips"
        else:
            key = "finish_arch"
        base["motion_key"] = key
        base["motion"] = templates.get(key) or base["motion"]
        if cb in {"internal_peak", "creampie_release"}:
            base["shot_size"] = "close-up"
            base["angle"] = "eye level"
            base["framing"] = (
                "vertical 9:16 close-up on peak reaction, bare skin contact visible, "
                "full head + headroom, safe framing no cropping, biological release readable"
            )
        elif cb == "deep_thrust":
            base["shot_size"] = "medium"
            base["angle"] = "slight low"
            base["framing"] = (
                "vertical 9:16 deep penetrating thrust visible, pelvis and thighs readable, "
                "full head + headroom, safe framing no cropping, skin-to-skin friction"
            )
        else:
            base["shot_size"] = "medium" if ph == "act" else "close-up"
            base["angle"] = "slight low" if ph == "act" else "eye level"
            base["framing"] = (
                "vertical 9:16 coitus-readable body, pelvis or finish reaction, "
                "full head + headroom, safe framing no cropping"
            )
        base["heat_phase"] = ph
    elif ph == "foreplay":
        key = "undress_slide"
        base["motion_key"] = key
        base["motion"] = templates.get(key) or base["motion"]
        base["heat_phase"] = ph
    return base


# Beats that often produce low motion_score on quiet close-ups — force micro cues.
MICRO_MOTION_BEATS = frozenset({"sensory", "reaction", "afterglow", "hook"})
# Substrings that count as present micro-motion (case-insensitive match on motion text)
MICRO_MOTION_CUES = (
    "blink",
    "breath",
    "tremble",
    "micro",
    "hair",
    "push-in",
    "push in",
    "sway",
    "tear",
    "flutter",
)
# Default micro fillers WITHOUT forced push-in (axis injected separately).
# IMPORTANT: micro is FILLER — for hook/approach/action the author's primary verb
# must already lead the motion string (lessons-2026-07-17-vo-motion-link).
MICRO_MOTION_SUFFIX = {
    "sensory": "soft blink, micro breath",
    "reaction": "soft blink, body micro-tremble",
    "afterglow": "soft blink, tear or breath micro-move",
    "hook": "soft blink, ambient micro-motion after primary action",
}


def inject_micro_motion_cues(
    motion: str,
    dramatic_function: str,
    *,
    camera_axis: str | None = None,
) -> str:
    """Append micro-motion cues for quiet beats when author text lacks them.

    Camera axis is chosen separately (rotate; never default every beat to push-in).
    Author text is preserved; only a suffix is added when needed.
    """
    text = (motion or "").strip()
    fn = (dramatic_function or "").strip().lower()
    if not text:
        defaults = coverage_defaults_for_beat(fn) if fn in BEAT_COVERAGE_DEFAULTS else None
        base = defaults["motion"] if defaults else "soft blink, idle not speaking"
        if camera_axis:
            return inject_camera_axis_phrase(base, camera_axis)
        return base
    if fn not in MICRO_MOTION_BEATS:
        if camera_axis and infer_camera_axis(text) is None:
            return inject_camera_axis_phrase(text, camera_axis)
        return text
    lowered = text.lower()
    # Do not "launder" mouth-speaking-primary motion by appending blink;
    # leave unchanged so validate_motion still rejects pure dialogue mouth cues.
    for pat in FORBIDDEN_MOTION_PATTERNS:
        if pat.search(lowered) and not any(
            h in lowered for h in ("idle", "blink", "breath", "camera", "push", "pan")
        ):
            return text
    out = text
    if not any(cue in lowered for cue in MICRO_MOTION_CUES):
        suffix = MICRO_MOTION_SUFFIX.get(fn, "soft blink")
        if "idle not speaking" in lowered:
            base = out
            if base.rstrip().endswith("idle not speaking"):
                base = base[: base.lower().rfind("idle not speaking")].rstrip(" ,;")
            out = f"{base}, {suffix}, idle not speaking"
        else:
            out = f"{out}, {suffix}, idle not speaking"
    if camera_axis and infer_camera_axis(out) is None:
        out = inject_camera_axis_phrase(out, camera_axis)

    if fn in {"hook", "approach", "action"}:
        out = (
            out.replace("soft lean", "lean hard")
            .replace("gentle sway", "decisive motion")
            .replace("soft breath", "sharp breath")
            .replace("fingers slowly", "fingers snap")
            .replace("hair drifts", "hair whips")
        )

    return out


def apply_coverage_defaults_to_shot(
    shot: dict[str, Any],
    *,
    dramatic_function: str,
    shot_index: int = 0,
    previous_axes: list[str] | None = None,
    previous_focal: str | None = None,
    previous_viewpoints: list[str] | None = None,
    previous_viewpoint: str | None = None,
    previous_look: str | None = None,
    previous_end_pose: str | None = None,
    cast_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Fill missing motion / camera / framing / camera_axis / stance from beat grammar.

    Explicit author values always win for shot_size/angle/framing/viewpoint/focal.
    Motion may receive micro-cue + rotating camera_axis injection.
    Character stance (focal/viewpoint/look_axis) elevates multi-POV cinema.
    When heat_phase/coitus_beat set, prefer adult coitus motion templates.
    Returns a report of what was filled / injected.
    """
    heat_phase = (
        str(shot.get("heat_phase") or (shot.get("dsl") or {}).get("heat_phase") or "")
        .strip()
        .lower()
        or None
    )
    coitus_beat = (
        str(shot.get("coitus_beat") or (shot.get("dsl") or {}).get("coitus_beat") or "")
        .strip()
        .lower()
        or None
    )
    defaults = coverage_defaults_for_heat(
        dramatic_function,
        heat_phase=heat_phase,
        coitus_beat=coitus_beat,
    )
    filled: list[str] = []
    injected = False
    dsl = shot.get("dsl")
    if not isinstance(dsl, dict):
        dsl = {}
        shot["dsl"] = dsl
    if heat_phase and not dsl.get("heat_phase"):
        dsl["heat_phase"] = heat_phase
    if coitus_beat and not dsl.get("coitus_beat"):
        dsl["coitus_beat"] = coitus_beat
        shot["coitus_beat"] = coitus_beat

    # --- Character stance (focal / viewpoint / look_axis) ---
    author_focal = dsl.get("focal_character") or shot.get("focal_character")
    if author_focal and str(author_focal).strip():
        focal = normalize_focal_character(author_focal)
        focal_source = "author"
    else:
        focal = suggest_focal_character(
            dramatic_function,
            previous_focal=previous_focal,
            cast_ids=cast_ids,
            shot_index=shot_index,
        )
        focal_source = "suggest"
        filled.append("dsl.focal_character")
    dsl["focal_character"] = focal
    shot["focal_character"] = focal

    author_vp = dsl.get("viewpoint") or shot.get("viewpoint")
    if author_vp and str(author_vp).strip():
        try:
            viewpoint = normalize_viewpoint(author_vp)
            vp_source = "author"
        except PolicyError:
            viewpoint = suggest_viewpoint(
                dramatic_function,
                focal=focal,
                previous_viewpoints=previous_viewpoints,
                previous_viewpoint=previous_viewpoint,
                previous_focal=previous_focal,
                shot_index=shot_index,
            )
            vp_source = "suggest_fallback"
            filled.append("dsl.viewpoint")
    else:
        viewpoint = suggest_viewpoint(
            dramatic_function,
            focal=focal,
            previous_viewpoints=previous_viewpoints,
            previous_viewpoint=previous_viewpoint,
            previous_focal=previous_focal,
            shot_index=shot_index,
        )
        vp_source = "suggest"
        filled.append("dsl.viewpoint")
    dsl["viewpoint"] = viewpoint
    shot["viewpoint"] = viewpoint
    vp_hints = viewpoint_coverage_hints(viewpoint)

    author_look = dsl.get("look_axis") or shot.get("look_axis")
    if author_look and str(author_look).strip():
        try:
            look_axis = normalize_look_axis(author_look)
            look_source = "author"
        except PolicyError:
            look_axis = suggest_look_axis(viewpoint, previous_look=previous_look)
            look_source = "suggest_fallback"
            filled.append("dsl.look_axis")
    else:
        look_axis = suggest_look_axis(viewpoint, previous_look=previous_look)
        look_source = "suggest"
        filled.append("dsl.look_axis")
    dsl["look_axis"] = look_axis

    # Resolve camera axis: author > infer from motion > rotate by beat
    author_axis = str(dsl.get("camera_axis") or "").strip().lower()
    if author_axis and author_axis in CAMERA_AXIS_MOTION_PHRASE:
        axis = author_axis
        axis_source = "author"
    else:
        inferred = infer_camera_axis(str(dsl.get("motion") or ""))
        if inferred:
            axis = inferred
            axis_source = "inferred"
        else:
            axis = suggest_camera_axis(
                dramatic_function,
                previous_axes=previous_axes,
                shot_index=shot_index,
            )
            axis_source = "suggest"
            filled.append("dsl.camera_axis")
    dsl["camera_axis"] = axis

    motion = dsl.get("motion")
    if not isinstance(motion, str) or not motion.strip():
        dsl["motion"] = inject_camera_axis_phrase(defaults["motion"], axis)
        filled.append("dsl.motion")
    else:
        # Never rewrite pure mouth-speaking (must fail validate_motion later)
        if _is_mouth_primary_only(motion):
            pass
        else:
            new_motion = inject_micro_motion_cues(motion, dramatic_function, camera_axis=axis)
            if new_motion != motion.strip():
                dsl["motion"] = new_motion
                injected = True
                filled.append("dsl.motion_micro_inject")
            elif (
                axis_source == "suggest"
                and infer_camera_axis(motion) is None
                and not _motion_has_camera_language(motion)
            ):
                dsl["motion"] = inject_camera_axis_phrase(motion, axis)
                if dsl["motion"] != motion.strip():
                    filled.append("dsl.motion_axis_inject")
    camera = dsl.get("camera")
    if not isinstance(camera, dict):
        camera = {}
        dsl["camera"] = camera
    shot_size = camera.get("shot_size")
    if not isinstance(shot_size, str) or not shot_size.strip():
        # stance-specific sizes only when viewpoint is non-objective (keep beat defaults otherwise)
        if viewpoint and viewpoint != "objective":
            camera["shot_size"] = vp_hints.get("shot_size") or defaults["shot_size"]
        else:
            camera["shot_size"] = defaults["shot_size"]
        filled.append("dsl.camera.shot_size")
    angle = camera.get("angle")
    if not isinstance(angle, str) or not angle.strip():
        if viewpoint and viewpoint != "objective":
            camera["angle"] = vp_hints.get("angle") or defaults.get("angle") or "eye level"
        else:
            camera["angle"] = defaults.get("angle") or "eye level"
        filled.append("dsl.camera.angle")
    framing = dsl.get("framing") or camera.get("framing")
    if not isinstance(framing, str) or not framing.strip():
        # merge beat framing + viewpoint stance hint
        base_fr = defaults.get("framing") or "vertical 9:16 balanced framing"
        hint = vp_hints.get("framing_hint") or ""
        look_bit = f"look_axis {look_axis}" if look_axis else ""
        focal_bit = f"focal {focal}" if focal else ""
        bits = [base_fr, hint, look_bit, focal_bit]
        dsl["framing"] = ", ".join(b for b in bits if b)
        camera.setdefault("framing", dsl["framing"])
        filled.append("dsl.framing")

    # --- Continuity Auto-Injection ---
    chain_mode = (dsl.get("chain_mode") or shot.get("chain_mode") or "").strip().lower()
    if chain_mode in {"continue", "match", "match_cut", "soft"} and previous_end_pose:
        author_start_pose = dsl.get("start_pose") or shot.get("start_pose")
        if not author_start_pose or not str(author_start_pose).strip():
            dsl["start_pose"] = previous_end_pose.strip()
            shot["start_pose"] = previous_end_pose.strip()
            filled.append("dsl.start_pose (auto-injected from previous end_pose)")

    report = {
        "dramatic_function": defaults["dramatic_function"],
        "filled": filled,
        "micro_motion_injected": injected,
        "camera_axis": axis,
        "camera_axis_source": axis_source,
        "focal_character": focal,
        "focal_source": focal_source,
        "viewpoint": viewpoint,
        "viewpoint_source": vp_source,
        "look_axis": look_axis,
        "look_axis_source": look_source,
        "defaults_used": {
            "shot_size": defaults["shot_size"],
            "angle": defaults.get("angle"),
            "framing": defaults.get("framing"),
            "motion_key": defaults["motion_key"],
            "camera_axis": axis,
            "viewpoint": viewpoint,
            "focal_character": focal,
        }
        if filled
        else {},
    }
    if filled:
        shot.setdefault("coverage_defaults_applied", report)
    return report


# ---------------------------------------------------------------------------
# Heat / wardrobe / sex arc — extracted to edit_policy_heat.py (C4 · 2026-08-04)
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Mixed-source EDL merge (generated clips + real footage) — video-use bridge
# 2026-07-23: lets the pipeline combine generated I2V clips with auto-cut real
# footage segments into one timeline. Honors video-use Hard Rule 1 (subtitles LAST)
# and Hard Rule 7 (pad cut edges).
# ---------------------------------------------------------------------------
# merge_edls extracted to edit_edl_merge.py — re-exported for backward compat.
from edit_edl_merge import merge_edls  # noqa: E402, F401
from edit_policy_heat import (  # noqa: E402, F401
    _DRAMATIC_TO_HEAT_PHASE,
    _ECCHI_COMPLETE,
    _ECCHI_DISTANCE,
    _ECCHI_DOUBLE,
    _ECCHI_POWER,
    _ECCHI_SENSORY,
    _ECCHI_WARDROBE,
    _EXPOSED_WARDROBE_MARKERS,
    _FULL_DRESS_MARKERS,
    _MALE_CAST_IDS,
    _MULTI_HEROINE_PROMPT_MARKERS,
    _NAR_EXTREME_MARKERS,
    _NAR_LITERARY_ONLY_HINTS,
    _NAR_MILD_ONLY_MARKERS,
    _NAR_SEX_VERB_MARKERS,
    _NAR_SPICE_MARKERS,
    _SEX_ARC_FOREPLAY_MARKERS,
    _SEX_ARC_PENETRATION_MARKERS,
    _SEX_ARC_RELEASE_MARKERS,
    _TEMPLATE_NAR_POLLUTION_MARKERS,
    _UNDRESS_ACTION_MARKERS,
    _WARDROBE_START_POSE_HINT,
    _WARDROBE_SUBJECT_MUST_INCLUDE,
    ADVISORY_MAX_INTIMACY_RATIO,
    ADVISORY_MAX_SETUP_RATIO,
    ADVISORY_MAX_SEX_DURATION_RATIO,
    COITUS_BEAT_DEFAULT_POSE,
    COITUS_BEATS,
    COITUS_REQUIRED_BEATS,
    DEFAULT_BARE_PEAK_REQUIRED,
    DEFAULT_SEX_DURATION_FLOOR,
    DEFAULT_SHOT_DURATION_SEC,
    ECCHI_CHECKLIST_ITEMS,
    EXTREME_INTIMACY_FLOOR,
    EXTREME_SETUP_CEILING,
    HARDCORE_CRAFT_SPINE,
    HARDCORE_SEX_DURATION_TARGET,
    HEAT_PHASE_ESCALATION_RANK,
    HEAT_PHASES,
    HEAT_SCALES,
    HOT_SEX_DURATION_FLOOR,
    INTIMACY_PHASES,
    MAX_PRE_CLIMAX_PLATEAU_SHOTS,
    PHASE_WARDROBE_FLOOR,
    SEX_ARC_BEATS,
    SEX_ARC_REQUIRED,
    SEX_PHASES,
    SEX_POSES,
    SEX_WARDROBE_OK,
    SEX_WARDROBE_STRONG,
    SPICE_LEVELS,
    WARDROBE_STATES,
    WARDROBE_UNDRESS_RANK,
    _ensure_start_pose_wardrobe,
    _is_detail_cu_shot,
    _merge_sub_issues,
    _shot_duration_sec,
    _shot_has_penetration_verb,
    _shot_has_release_marker,
    _shot_size_rank,
    _shot_visual_blob,
    _shot_visual_pose_blob,
    _write_shot_wardrobe_state,
    apply_heat_phase_defaults,
    apply_impact_boost_patches,
    apply_vo_spice_auto,
    apply_wardrobe_continuity,
    compute_erotic_impact_score,
    heat_phase_escalation_rank,
    infer_heat_phase,
    is_template_nar_pollution,
    lint_both_undress,
    lint_coitus_grammar,
    lint_ecchi_checklist,
    lint_heat_arc,
    lint_heat_escalation_challenge,
    lint_montage_craft,
    lint_multi_heroine,
    lint_sex_arc,
    lint_sex_detail_cu,
    lint_sex_pose_variety,
    lint_sex_vo_spice,
    lint_sex_wardrobe,
    lint_size_ladder,
    lint_user_source_fidelity,
    lint_vo_motion_align,
    nar_has_extreme_spice,
    nar_has_sex_verb,
    nar_has_spice,
    normalize_heat_phase,
    normalize_heat_scale,
    normalize_spice_level,
    normalize_wardrobe_state,
    resolve_coitus_beat,
    resolve_heroine_cast_mode,
    resolve_partner_wardrobe_state,
    resolve_sex_arc_beat,
    resolve_sex_pose,
    resolve_wardrobe_state,
    shot_coitus_pseudo_only,
    shot_coitus_readable,
    shot_has_undress_action,
    suggest_impact_boost_actions,
    suggest_vo_lines,
    wardrobe_undress_rank,
)

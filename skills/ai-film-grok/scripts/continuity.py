#!/usr/bin/env python3
"""Continuity lint for film-spec (stable reason codes, pre-spend gate)."""

from __future__ import annotations

from typing import Any

# Stable reason codes (do not rename lightly — agents and tests depend on them)
CODE_CAST_FLIP = "CAST_FLIP"
CODE_COVERAGE_JUMP = "COVERAGE_JUMP"
CODE_SCREEN_DIRECTION_FLIP = "SCREEN_DIRECTION_FLIP"
CODE_PROP_DROP = "PROP_DROP"
CODE_BEAT_ISOLATION = "BEAT_ISOLATION"
# VO–motion linkage / anti-fatigue (soft by default; see lessons-2026-07-17-vo-motion-link)
CODE_PRIMARY_MOTION_WEAK = "PRIMARY_MOTION_WEAK"
CODE_MOTION_MONOTONY = "MOTION_MONOTONY"
CODE_SIZE_FLAT = "SIZE_FLAT"
CODE_SOFT_SOUP = "SOFT_SOUP"
CODE_CAMERA_AXIS_FLAT = "CAMERA_AXIS_FLAT"
CODE_STYLE_SOUP = "STYLE_SOUP"
# Frame chain: soft/hold joins must declare end_pose → start_pose (lessons-2026-07-20-frame-chain)
CODE_FRAME_CHAIN_GAP = "FRAME_CHAIN_GAP"
CODE_FRAME_CHAIN_ORPHAN = "FRAME_CHAIN_ORPHAN"
# Meaningful motion: dynamics must carry story (lessons-2026-07-20-meaningful-motion)
CODE_MOTION_NO_MEANING = "MOTION_NO_MEANING"
CODE_BEAT_SEMANTICS_MISS = "BEAT_SEMANTICS_MISS"
CODE_VISIBLE_CHANGE_MISSING = "VISIBLE_CHANGE_MISSING"
# P1-5: scene must have locationId (was hardcoded None in derive_graph)
CODE_SCENE_LOCATION_MISSING = "SCENE_LOCATION_MISSING"
CODE_CHARACTER_STATE_REGRESSION = "CHARACTER_STATE_REGRESSION"
CODE_POSE_MONOTONY = "POSE_MONOTONY"
CODE_SIZE_MONOTONY = "SIZE_MONOTONY"
CODE_GAZE_MISALIGNMENT = "GAZE_MISALIGNMENT"
CODE_AXIS_JUMP = "AXIS_JUMP"

# Micro-motion fillers — allowed as support, not as sole motion for hook/approach/action
_MICRO_ONLY_TOKENS = frozenset(
    {
        "blink",
        "breath",
        "breathing",
        "tremble",
        "micro",
        "hair",
        "push-in",
        "push",
        "in",
        "sway",
        "flutter",
        "idle",
        "not",
        "speaking",
        "slow",
        "continuous",
        "soft",
        "gentle",
        "subtle",
        "ambient",
        "drift",
        "strand",
        "hold",
        "camera",
        "shallow",
        "focus",
        "rim",
        "glow",
        "lamp",
        "and",
        "with",
        "the",
        "a",
        "an",
        "or",
        "of",
        "to",
        "on",
        "at",
    }
)

# Verbs/objects that count as primary visible action (substring match on motion+action)
_PRIMARY_ACTION_MARKERS = (
    "latch",
    "unhook",
    "buckle",
    "belt",
    "coat",
    "slide",
    "slip",
    "lean",
    "step",
    "walk",
    "turn",
    "pull",
    "push",
    "extend",
    "reach",
    "open",
    "close",
    "shut",
    "settle",
    "recline",
    "beckon",
    "point",
    "touch",
    "grip",
    "grab",
    "glance",
    "look",
    "smile",
    "unbutton",
    "unzip",
    "remove",
    "drop",
    "hand",
    "finger",
    "door",
    "shoulder",
    "hip",
    "sit",
    "stand",
    "kneel",
    "tilt",
    "bow",
    "approach",
    "track",
    "dolly",
    "pan",
    "orbit",
)

SHOT_SIZE_RANK = {
    "extreme close-up": 0,
    "ecu": 0,
    "close-up": 1,
    "cu": 1,
    "medium close-up": 2,
    "mcu": 2,
    "medium": 3,
    "ms": 3,
    "medium full": 4,
    "mfs": 4,
    "full": 5,
    "fs": 5,
    "wide": 6,
    "ws": 6,
    "extreme wide": 7,
    "ews": 7,
}


class ContinuityLintError(ValueError):
    pass


def _norm_token(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.strip().lower().split())


def _shot_size_rank(size: object) -> int | None:
    key = _norm_token(size)
    if not key:
        return None
    if key in SHOT_SIZE_RANK:
        return SHOT_SIZE_RANK[key]
    # fuzzy contains
    for name, rank in SHOT_SIZE_RANK.items():
        if name in key or key in name:
            return rank
    return None


def _cast_set(shot: dict[str, Any]) -> set[str]:
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    cast = dsl.get("cast")
    if isinstance(cast, list):
        return {_norm_token(c) for c in cast if _norm_token(c)}
    if isinstance(cast, str) and cast.strip():
        return {_norm_token(cast)}
    return set()


def _props_set(shot: dict[str, Any]) -> set[str]:
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    props = dsl.get("props") or dsl.get("prop")
    if isinstance(props, list):
        return {_norm_token(p) for p in props if _norm_token(p)}
    if isinstance(props, str) and props.strip():
        return {_norm_token(props)}
    return set()


def _screen_direction(shot: dict[str, Any]) -> str:
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    cam = dsl.get("camera") if isinstance(dsl.get("camera"), dict) else {}
    for key in ("screen_direction", "axis", "look_direction"):
        if shot.get(key):
            return _norm_token(shot.get(key))
        if dsl.get(key):
            return _norm_token(dsl.get(key))
        if cam.get(key):
            return _norm_token(cam.get(key))
    return ""


def _motion_action_blob(shot: dict[str, Any]) -> str:
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    parts = [
        str(dsl.get("motion") or ""),
        str(dsl.get("action") or ""),
    ]
    return _norm_token(" ".join(parts))


def _has_primary_action(shot: dict[str, Any]) -> bool:
    """True if motion/action names a concrete body/prop verb beyond micro fillers."""
    blob = _motion_action_blob(shot)
    if not blob:
        return False
    # Normalize hyphens so "push-in" splits into micro tokens push + in
    cleaned = blob.replace(",", " ").replace(";", " ").replace("/", " ").replace("-", " ")
    tokens = [t for t in cleaned.split() if t and t not in _MICRO_ONLY_TOKENS]
    if not tokens:
        return False
    # Token membership (not raw substring) so "push-in" alone does not count as primary
    if any(m in tokens for m in _PRIMARY_ACTION_MARKERS):
        return True
    # Longer leftover words (e.g. character-specific props) count as primary
    return any(len(t) >= 5 for t in tokens)


def _shot_size_band(size: object) -> str:
    """Collapse ranks into 3 bands for anti-fatigue (wide / mid / tight)."""
    r = _shot_size_rank(size)
    if r is None:
        return ""
    if r <= 1:
        return "tight"
    if r <= 3:
        return "mid"
    return "wide"


def _angle_bucket(shot: dict[str, Any]) -> str:
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    cam = dsl.get("camera") if isinstance(dsl.get("camera"), dict) else {}
    ang = _norm_token(cam.get("angle") or dsl.get("angle") or "")
    if not ang:
        return ""
    if "low" in ang:
        return "low"
    if "high" in ang or "top" in ang:
        return "high"
    if "profile" in ang or "side" in ang:
        return "profile"
    if "pov" in ang or "over" in ang:
        return "pov"
    return "eye"


def lint_vo_motion_link(
    shots: list[dict[str, Any]],
    *,
    transition_intents: list[str] | None = None,
) -> dict[str, Any]:
    """Soft lint: primary action strength, 3-shot monotony, size flatness, soft-soup joins.

    Does not block write-spec unless vo_motion_strict is set by caller.
    Codes: PRIMARY_MOTION_WEAK, MOTION_MONOTONY, SIZE_FLAT, SOFT_SOUP.
    """
    issues: list[dict[str, Any]] = []
    if not shots:
        return {
            "ok": True,
            "issues": [],
            "codes": [],
            "error_count": 0,
            "warning_count": 0,
            "blocking": [],
        }

    need_primary = frozenset({"hook", "approach", "action"})
    for i, shot in enumerate(shots):
        sid = str(shot.get("id") or f"shot{i + 1}")
        fn = _norm_token(shot.get("dramatic_function"))
        if fn in need_primary and not _has_primary_action(shot):
            issues.append(
                {
                    "code": CODE_PRIMARY_MOTION_WEAK,
                    "severity": "warning",
                    "message": (
                        f"{sid} beat={fn}: motion/action lacks a primary body/prop verb "
                        "(only blink/breath/push-in fillers). Bind nar to a visible action."
                    ),
                    "shot_ids": [sid],
                }
            )

    # 3-shot monotony / size flat
    for i in range(0, len(shots) - 2):
        window = shots[i : i + 3]
        ids = [str(s.get("id") or f"shot{i + j + 1}") for j, s in enumerate(window)]
        primaries = [_has_primary_action(s) for s in window]
        if not any(primaries):
            issues.append(
                {
                    "code": CODE_MOTION_MONOTONY,
                    "severity": "warning",
                    "message": (
                        f"{ids[0]}..{ids[2]}: three consecutive shots lack primary action "
                        "(micro-motion monotony — viewer fatigue)"
                    ),
                    "shot_ids": ids,
                }
            )
        bands = []
        angles = []
        for s in window:
            dsl = s.get("dsl") if isinstance(s.get("dsl"), dict) else {}
            cam = dsl.get("camera") if isinstance(dsl.get("camera"), dict) else {}
            bands.append(_shot_size_band(cam.get("shot_size")))
            angles.append(_angle_bucket(s))
        if bands and all(b and b == bands[0] for b in bands):
            issues.append(
                {
                    "code": CODE_SIZE_FLAT,
                    "severity": "warning",
                    "message": (
                        f"{ids[0]}..{ids[2]}: three consecutive shots stay in band "
                        f"{bands[0]!r} — vary shot_size (wide/mid/tight)"
                    ),
                    "shot_ids": ids,
                }
            )
        # diversity score: primary variation + band + angle
        diversify = 0
        if len(set(bands)) >= 2:
            diversify += 1
        if len(set(a for a in angles if a)) >= 2:
            diversify += 1
        if sum(1 for p in primaries if p) >= 2 and not all(primaries):
            diversify += 1
        elif sum(primaries) == 3:
            # all have primary — check if motion blobs are near-identical
            blobs = {_motion_action_blob(s)[:48] for s in window}
            if len(blobs) >= 2:
                diversify += 1
        if diversify < 2 and len(window) == 3:
            # only add if not already monotony/size_flat for same window
            already = any(
                iss.get("shot_ids") == ids and iss["code"] in {CODE_MOTION_MONOTONY, CODE_SIZE_FLAT}
                for iss in issues
            )
            if not already and diversify <= 1:
                issues.append(
                    {
                        "code": CODE_MOTION_MONOTONY,
                        "severity": "warning",
                        "message": (
                            f"{ids[0]}..{ids[2]}: low visual variety "
                            "(need ≥2 of: size-band change, angle change, distinct primary verbs)"
                        ),
                        "shot_ids": ids,
                    }
                )

    # Soft-soup: many soft joins, no hard punctuation (60s films)
    if transition_intents and len(transition_intents) >= 5:
        soft_n = sum(1 for t in transition_intents if str(t).strip().lower() == "soft")
        hard_n = sum(1 for t in transition_intents if str(t).strip().lower() == "hard")
        if soft_n >= 5 and hard_n == 0:
            issues.append(
                {
                    "code": CODE_SOFT_SOUP,
                    "severity": "warning",
                    "message": (
                        f"transition_intents has {soft_n} soft and 0 hard — "
                        "add ≥1 hard join per ~5 soft for rhythm (not slideshow soup)"
                    ),
                    "shot_ids": [],
                }
            )
        # Ratio soup: soft dominates hard too heavily (e.g. 7 soft / 1 hard)
        if soft_n >= 4 and hard_n > 0 and soft_n >= hard_n * 4:
            issues.append(
                {
                    "code": CODE_SOFT_SOUP,
                    "severity": "warning",
                    "message": (
                        f"transition_intents soft:hard = {soft_n}:{hard_n} — "
                        "prefer ~1 hard every 2 soft for 60s vertical shorts"
                    ),
                    "shot_ids": [],
                }
            )

    # Camera axis flat: 3 consecutive same camera_axis (or all push-in language)
    for i in range(0, len(shots) - 2):
        window = shots[i : i + 3]
        ids = [str(s.get("id") or f"shot{i + j + 1}") for j, s in enumerate(window)]
        axes: list[str] = []
        for s in window:
            dsl = s.get("dsl") if isinstance(s.get("dsl"), dict) else {}
            ax = str(dsl.get("camera_axis") or "").strip().lower()
            if not ax:
                blob = _motion_action_blob(s)
                if any(k in blob for k in ("push", "dolly")):
                    ax = "dolly_in"
                elif "pan" in blob:
                    ax = "pan_with"
                elif "locked" in blob or "static" in blob:
                    ax = "locked"
                elif "pull" in blob:
                    ax = "pull_back"
            axes.append(ax)
        if axes and all(a and a == axes[0] for a in axes):
            issues.append(
                {
                    "code": CODE_CAMERA_AXIS_FLAT,
                    "severity": "warning",
                    "message": (
                        f"{ids[0]}..{ids[2]}: three consecutive shots share camera_axis "
                        f"{axes[0]!r} — rotate dolly_in / pan_with / locked / ecu_hold / "
                        "low_lean / pull_back (男娘咖啡厅运镜防腻)"
                    ),
                    "shot_ids": ids,
                }
            )

    codes = sorted({iss["code"] for iss in issues})
    return {
        "ok": len(issues) == 0,
        "issues": issues,
        "codes": codes,
        "error_count": 0,
        "warning_count": len(issues),
        "blocking": [],
    }


def lint_transition_styles(
    styles: list[str] | None,
    *,
    join_intents: list[str] | None = None,
) -> dict[str, Any]:
    """Soft lint: soft/hold joins must not all use the same xfade style (style soup)."""
    issues: list[dict[str, Any]] = []
    if not styles or len(styles) < 3:
        return {
            "ok": True,
            "issues": [],
            "codes": [],
            "error_count": 0,
            "warning_count": 0,
            "blocking": [],
        }
    soft_styles: list[str] = []
    for i, st in enumerate(styles):
        intent = ""
        if join_intents and i < len(join_intents):
            intent = str(join_intents[i]).strip().lower()
        if intent == "hard":
            continue
        soft_styles.append(str(st).strip().lower())
    if len(soft_styles) >= 3 and len(set(soft_styles)) == 1:
        issues.append(
            {
                "code": CODE_STYLE_SOUP,
                "severity": "warning",
                "message": (
                    f"transition_styles soft/hold all {soft_styles[0]!r} — "
                    "rotate fade/smoothleft/hblur/dissolve/fadeblack"
                ),
                "shot_ids": [],
            }
        )
    codes = sorted({iss["code"] for iss in issues})
    return {
        "ok": len(issues) == 0,
        "issues": issues,
        "codes": codes,
        "error_count": 0,
        "warning_count": len(issues),
        "blocking": [],
    }


# Beat → story-readable motion tokens (substring match on action+motion+visible_change)
_BEAT_SEMANTIC_MARKERS: dict[str, tuple[str, ...]] = {
    "hook": (
        "enter",
        "step",
        "open",
        "appear",
        "pull",
        "reveal",
        "arrive",
        "curtain",
        "door",
        "threshold",
        "walk",
        "turn",
        "emerge",
    ),
    "approach": (
        "step",
        "lean",
        "close",
        "near",
        "reach",
        "latch",
        "walk",
        "toward",
        "approach",
        "shut",
        "lock",
        "draw",
        "narrow",
    ),
    "sensory": (
        "breath",
        "sweat",
        "bead",
        "tremble",
        "shiver",
        "pulse",
        "hair",
        "skin",
        "collarbone",
        "heat",
        "drip",
        "shine",
        "rise",
    ),
    "reaction": (
        "look",
        "glance",
        "wink",
        "flinch",
        "smile",
        "blush",
        "heart",
        "gaze",
        "eyes",
        "hand",
        "gesture",
        "startle",
    ),
    "action": (
        "plant",
        "lean",
        "push",
        "pull",
        "grab",
        "press",
        "lock",
        "unhook",
        "grip",
        "slam",
        "strike",
        "throw",
        "lift",
        "drop",
        "vanity",
        "table",
    ),
    "afterglow": (
        "hold",
        "blink",
        "linger",
        "residual",
        "settle",
        "pull-back",
        "pullback",
        "soften",
        "still",
        "exhale",
    ),
    "bridge": (
        "pan",
        "track",
        "pass",
        "cross",
        "corridor",
        "transition",
        "dolly",
        "follow",
    ),
}

# Pure aesthetic filler that does not advance story alone
_AESTHETIC_ONLY = frozenset(
    {
        "slow",
        "push",
        "push-in",
        "pushin",
        "dolly",
        "blink",
        "breath",
        "breathing",
        "idle",
        "not",
        "speaking",
        "soft",
        "gentle",
        "subtle",
        "hair",
        "drift",
        "sway",
        "ambient",
        "cinematic",
        "beautiful",
        "moody",
        "atmosphere",
        "camera",
        "continuous",
        "micro",
        "hold",
        "pose",
        "current",
        "from",
        "then",
        "and",
        "with",
        "the",
        "a",
        "an",
    }
)


def lint_meaningful_motion(shots: list[dict[str, Any]]) -> dict[str, Any]:
    """Soft lint: each shot's motion must carry beat-readable story meaning.

    Codes: MOTION_NO_MEANING, BEAT_SEMANTICS_MISS, VISIBLE_CHANGE_MISSING.
    See references/lessons-2026-07-20-meaningful-motion.md
    """
    issues: list[dict[str, Any]] = []
    if not shots:
        return {
            "ok": True,
            "issues": [],
            "codes": [],
            "error_count": 0,
            "warning_count": 0,
            "blocking": [],
        }

    for i, shot in enumerate(shots):
        sid = str(shot.get("id") or f"shot{i + 1}")
        fn = _norm_token(shot.get("dramatic_function"))
        dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
        blob = _motion_action_blob(shot)
        visible = _norm_token(dsl.get("visible_change") or shot.get("visible_change") or "")
        story_beat = _norm_token(dsl.get("story_beat") or shot.get("story_beat") or "")
        # 1) Aesthetic-only motion (camera micro fillers without story body)
        cleaned = blob.replace(",", " ").replace(";", " ").replace("/", " ").replace("-", " ")
        tokens = [t for t in cleaned.split() if t]
        content = [t for t in tokens if t not in _AESTHETIC_ONLY and len(t) > 2]
        need_body = frozenset({"hook", "approach", "action"})
        if fn in need_body and len(content) < 2 and not visible:
            issues.append(
                {
                    "code": CODE_MOTION_NO_MEANING,
                    "severity": "warning",
                    "message": (
                        f"{sid} beat={fn}: motion looks aesthetic-only "
                        "(camera/blink/breath fillers without story body). "
                        "Write a visible world-change verb matching nar."
                    ),
                    "shot_ids": [sid],
                }
            )

        # 2) Beat semantics: action/motion should include beat-family tokens
        markers = _BEAT_SEMANTIC_MARKERS.get(fn) or ()
        if markers and blob:
            if not any(m in blob for m in markers):
                issues.append(
                    {
                        "code": CODE_BEAT_SEMANTICS_MISS,
                        "severity": "warning",
                        "message": (
                            f"{sid} beat={fn}: action/motion missing beat semantics "
                            f"(expect one of {list(markers)[:8]}…). "
                            "Dynamics must answer the beat's story question."
                        ),
                        "shot_ids": [sid],
                    }
                )

        # 3) Encourage explicit visible_change / story_beat on story drives
        if fn in need_body and not visible and not story_beat:
            # only warn if also weak primary — avoid noise when action is strong
            if not _has_primary_action(shot):
                issues.append(
                    {
                        "code": CODE_VISIBLE_CHANGE_MISSING,
                        "severity": "warning",
                        "message": (
                            f"{sid}: add dsl.visible_change (what changes in-world this shot) "
                            "or dsl.story_beat (one-line dramatic meaning)."
                        ),
                        "shot_ids": [sid],
                    }
                )

    codes = sorted({iss["code"] for iss in issues})
    return {
        "ok": len(issues) == 0,
        "issues": issues,
        "codes": codes,
        "error_count": 0,
        "warning_count": len(issues),
        "blocking": [],
    }


def _pose_fields(shot: dict[str, Any]) -> tuple[str, str, str]:
    """Return (start_pose, end_pose, chain_mode) normalized."""
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    start = _norm_token(dsl.get("start_pose") or shot.get("start_pose") or "")
    end = _norm_token(dsl.get("end_pose") or shot.get("end_pose") or "")
    mode = _norm_token(dsl.get("chain_mode") or shot.get("chain_mode") or "")
    return start, end, mode


def lint_frame_chain(
    shots: list[dict[str, Any]],
    *,
    transition_intents: list[str] | None = None,
) -> dict[str, Any]:
    """Soft lint: soft/hold joins need end_pose→start_pose chain fields.

    Grok I2V is frame-1 only; agents must chain via last-frame seed stills.
    Codes: FRAME_CHAIN_GAP, FRAME_CHAIN_ORPHAN.
    """
    issues: list[dict[str, Any]] = []
    if not shots or len(shots) < 2:
        return {
            "ok": True,
            "issues": [],
            "codes": [],
            "error_count": 0,
            "warning_count": 0,
            "blocking": [],
        }

    for i in range(1, len(shots)):
        prev, cur = shots[i - 1], shots[i]
        pid = str(prev.get("id") or f"shot{i}")
        cid = str(cur.get("id") or f"shot{i + 1}")
        pair = [pid, cid]
        join = "soft"
        if isinstance(transition_intents, list) and (i - 1) < len(transition_intents):
            join = _norm_token(transition_intents[i - 1]) or "soft"
        if join == "hard":
            continue

        p_start, p_end, p_mode = _pose_fields(prev)
        c_start, c_end, c_mode = _pose_fields(cur)

        if not p_end or not c_start:
            missing = []
            if not p_end:
                missing.append(f"{pid}.end_pose")
            if not c_start:
                missing.append(f"{cid}.start_pose")
            issues.append(
                {
                    "code": CODE_FRAME_CHAIN_GAP,
                    "severity": "warning",
                    "message": (
                        f"soft/hold join {pid}→{cid} missing pose chain ({', '.join(missing)}). "
                        "Grok is frame-1 only: extract last frame of prev clip, image_edit next still "
                        "from that seed; write end_pose/start_pose. See lessons-2026-07-20-frame-chain.md"
                    ),
                    "shot_ids": pair,
                    "join": join,
                }
            )

        # Orphan: soft join but author marked cut without bridge beat
        cur_fn = _norm_token(cur.get("dramatic_function"))
        if c_mode == "cut" and join != "hard" and cur_fn != "bridge":
            issues.append(
                {
                    "code": CODE_FRAME_CHAIN_ORPHAN,
                    "severity": "warning",
                    "message": (
                        f"{cid} chain_mode=cut on soft/hold join from {pid} — "
                        "use join=hard or chain_mode=continue + last-frame seed"
                    ),
                    "shot_ids": pair,
                    "join": join,
                }
            )
        if not c_mode and join in {"soft", "hold"} and p_end and c_start:
            # fields present but mode omitted — ok, default continue
            pass

    codes = sorted({iss["code"] for iss in issues})
    return {
        "ok": len(issues) == 0,
        "issues": issues,
        "codes": codes,
        "error_count": 0,
        "warning_count": len(issues),
        "blocking": [],
    }


def lint_continuity(
    shots: list[dict[str, Any]],
    *,
    fail_on: frozenset[str] | set[str] | None = None,
) -> dict[str, Any]:
    """Lint adjacent shots for continuity issues.

    Returns {ok, issues:[{code, severity, message, shot_ids}], codes: set-like list}.
    fail_on: codes treated as errors (ok=False). Default: CAST_FLIP, SCREEN_DIRECTION_FLIP.
    """
    if fail_on is None:
        fail_on = frozenset({CODE_CAST_FLIP, CODE_SCREEN_DIRECTION_FLIP})
    issues: list[dict[str, Any]] = []
    if not shots:
        return {"ok": True, "issues": [], "codes": [], "error_count": 0, "warning_count": 0}

    for i in range(1, len(shots)):
        prev, cur = shots[i - 1], shots[i]
        pid = str(prev.get("id") or f"shot{i}")
        cid = str(cur.get("id") or f"shot{i + 1}")
        pair = [pid, cid]
        prev_fn = _norm_token(prev.get("dramatic_function"))
        cur_fn = _norm_token(cur.get("dramatic_function"))

        # Cast flip: both declare cast and disjoint without bridge
        pc, cc = _cast_set(prev), _cast_set(cur)
        if pc and cc and pc.isdisjoint(cc) and cur_fn != "bridge" and prev_fn != "bridge":
            issues.append(
                {
                    "code": CODE_CAST_FLIP,
                    "severity": "error",
                    "message": f"adjacent shots change cast entirely ({sorted(pc)} → {sorted(cc)}) without bridge",
                    "shot_ids": pair,
                }
            )

        # Coverage jump: rank delta >= 4 without bridge/sensory exception
        prev_dsl = prev.get("dsl") if isinstance(prev.get("dsl"), dict) else {}
        cur_dsl = cur.get("dsl") if isinstance(cur.get("dsl"), dict) else {}
        prev_cam = prev_dsl.get("camera") if isinstance(prev_dsl.get("camera"), dict) else {}
        cur_cam = cur_dsl.get("camera") if isinstance(cur_dsl.get("camera"), dict) else {}
        r0 = _shot_size_rank(prev_cam.get("shot_size"))
        r1 = _shot_size_rank(cur_cam.get("shot_size"))
        if r0 is not None and r1 is not None and abs(r0 - r1) >= 4:
            if cur_fn not in {"bridge", "sensory", "hook"} and prev_fn not in {"bridge"}:
                issues.append(
                    {
                        "code": CODE_COVERAGE_JUMP,
                        "severity": "warning",
                        "message": f"shot_size jumps rank {r0}→{r1} without bridge/sensory beat",
                        "shot_ids": pair,
                    }
                )

        # Screen direction flip without axis-break intent
        d0, d1 = _screen_direction(prev), _screen_direction(cur)
        if d0 and d1 and d0 != d1:
            axis_ok = any(
                x
                in (
                    prev_fn,
                    cur_fn,
                    _norm_token(cur.get("axis_break")),
                    _norm_token(prev.get("axis_break")),
                )
                for x in ("bridge", "axis_break", "true", "yes")
            ) or bool(cur.get("axis_break") or prev.get("axis_break"))
            if not axis_ok:
                issues.append(
                    {
                        "code": CODE_SCREEN_DIRECTION_FLIP,
                        "severity": "error",
                        "message": f"screen_direction flips {d0!r}→{d1!r} without axis_break/bridge",
                        "shot_ids": pair,
                    }
                )

        # Prop drop: prev had props, cur empty after approach/action
        pp, cp = _props_set(prev), _props_set(cur)
        if (
            pp
            and not cp
            and prev_fn in {"approach", "action", "sensory"}
            and cur_fn not in {"bridge", "afterglow"}
        ):
            issues.append(
                {
                    "code": CODE_PROP_DROP,
                    "severity": "warning",
                    "message": f"props {sorted(pp)} disappear between shots without afterglow/bridge",
                    "shot_ids": pair,
                }
            )

        # Character state regression check (wardrobe / hair / skin / arousal level regression)
        w0 = str(
            prev.get("wardrobe_state")
            or (prev.get("dsl") if isinstance(prev.get("dsl"), dict) else {}).get("wardrobe_state")
            or ""
        ).lower()
        w1 = str(
            cur.get("wardrobe_state")
            or (cur.get("dsl") if isinstance(cur.get("dsl"), dict) else {}).get("wardrobe_state")
            or ""
        ).lower()
        w_ranks = {"full": 0, "loosened": 1, "partial": 2, "undressed": 3, "bare": 4}
        if w0 in w_ranks and w1 in w_ranks and w_ranks[w1] < w_ranks[w0]:
            issues.append(
                {
                    "code": CODE_CHARACTER_STATE_REGRESSION,
                    "severity": "warning",
                    "message": f"character wardrobe_state regressed from {w0!r} to {w1!r} without scene reset",
                    "shot_ids": pair,
                }
            )

        # Gaze misalignment check (abrupt break from intense eye contact without transition)
        g0 = str(prev.get("gaze_target") or prev.get("gazeTarget") or "").strip().lower()
        g1 = str(cur.get("gaze_target") or cur.get("gazeTarget") or "").strip().lower()
        if g0 == "intense_eye_contact" and g1 in {"gaze_away_abrupt", "gaze_away"}:
            issues.append(
                {
                    "code": CODE_GAZE_MISALIGNMENT,
                    "severity": "warning",
                    "message": f"gaze target abruptly broke from {g0!r} to {g1!r} without transition",
                    "shot_ids": pair,
                }
            )

        # 180-degree camera axis jump check (e.g. over_right_shoulder to over_left_shoulder)
        a0 = (
            str(
                prev.get("camera_axis")
                or prev.get("cameraMovement")
                or (prev.get("dsl") if isinstance(prev.get("dsl"), dict) else {}).get("camera_axis")
                or ""
            )
            .strip()
            .lower()
        )
        a1 = (
            str(
                cur.get("camera_axis")
                or cur.get("cameraMovement")
                or (cur.get("dsl") if isinstance(cur.get("dsl"), dict) else {}).get("camera_axis")
                or ""
            )
            .strip()
            .lower()
        )
        if (a0 == "over_right_shoulder" and a1 == "over_left_shoulder") or (
            a0 == "over_left_shoulder" and a1 == "over_right_shoulder"
        ):
            issues.append(
                {
                    "code": CODE_AXIS_JUMP,
                    "severity": "warning",
                    "message": f"camera axis crossed 180-degree line between {a0!r} and {a1!r} without neutral cut",
                    "shot_ids": pair,
                }
            )

    # 3-shot sliding window check for pose and framing monotony
    for i in range(len(shots) - 2):
        s0, s1, s2 = shots[i], shots[i + 1], shots[i + 2]
        p0 = (
            str(
                s0.get("sex_pose")
                or s0.get("sexPose")
                or (s0.get("dsl") if isinstance(s0.get("dsl"), dict) else {}).get("sex_pose")
                or ""
            )
            .strip()
            .lower()
        )
        p1 = (
            str(
                s1.get("sex_pose")
                or s1.get("sexPose")
                or (s1.get("dsl") if isinstance(s1.get("dsl"), dict) else {}).get("sex_pose")
                or ""
            )
            .strip()
            .lower()
        )
        p2 = (
            str(
                s2.get("sex_pose")
                or s2.get("sexPose")
                or (s2.get("dsl") if isinstance(s2.get("dsl"), dict) else {}).get("sex_pose")
                or ""
            )
            .strip()
            .lower()
        )
        if p0 and p0 == p1 == p2:
            issues.append(
                {
                    "code": CODE_POSE_MONOTONY,
                    "severity": "warning",
                    "message": f"3 consecutive shots use identical sex_pose {p0!r}",
                    "shot_ids": [str(s0.get("id")), str(s1.get("id")), str(s2.get("id"))],
                }
            )

        z0 = str(s0.get("shot_size") or s0.get("shotSize") or "").strip().lower()
        z1 = str(s1.get("shot_size") or s1.get("shotSize") or "").strip().lower()
        z2 = str(s2.get("shot_size") or s2.get("shotSize") or "").strip().lower()
        if z0 and z0 == z1 == z2:
            issues.append(
                {
                    "code": CODE_SIZE_MONOTONY,
                    "severity": "warning",
                    "message": f"3 consecutive shots use identical shot_size {z0!r}",
                    "shot_ids": [str(s0.get("id")), str(s1.get("id")), str(s2.get("id"))],
                }
            )

    codes = sorted({iss["code"] for iss in issues})
    # ok false only if any issue code is in fail_on
    blocking = [iss for iss in issues if iss["code"] in fail_on]
    return {
        "ok": len(blocking) == 0,
        "issues": issues,
        "codes": codes,
        "error_count": len(blocking),
        "warning_count": len(issues) - len(blocking),
        "blocking": blocking,
    }


def assert_continuity_or_raise(
    shots: list[dict[str, Any]],
    *,
    strict: bool = False,
) -> dict[str, Any]:
    """If strict and lint fails, raise ContinuityLintError with codes."""
    report = lint_continuity(shots)
    if strict and not report["ok"]:
        codes = ",".join(report["codes"])
        raise ContinuityLintError(f"continuity lint failed: {codes}")
    return report

"""Shot planning: vertical composition, camera, and shot expansion.

Extracted from story_plan.py to separate shot-planning logic from
beat extraction and graph construction.
"""

from __future__ import annotations

import re
from typing import Any

from beat_extraction import AUTHORING_PLACEHOLDER, _sentences


def _clip_nar(text: str, max_chars: int = 55) -> str:
    """Clip narration text to max_chars with ellipsis."""
    t = re.sub(r"\s+", " ", (text or "").strip())
    if not t:
        return "……"
    if len(t) <= max_chars:
        return t
    return t[: max_chars - 1] + "…"


def _est_vo_sec(nar: str) -> float:
    """Match film_spec.estimate_nar_vo_sec (zh ≈ 4 chars/s)."""
    t = (nar or "").strip()
    if not t:
        return 0.0
    return max(1.0, round(len(t) / 4.0, 2))


def _duration_for_nar(nar: str, floor: float = 3.0) -> float:
    """Ensure write-spec vo_pacing: est_vo ≤ duration + 0.5."""
    need = _est_vo_sec(nar) + 0.5 + 0.05
    return max(float(floor), round(need, 1))


# film-spec dramatic_function enum (kept here for shot-level decisions)
DRAMATIC_FUNCS = (
    "hook",
    "approach",
    "sensory",
    "reaction",
    "action",
    "afterglow",
    "bridge",
)


def _vertical_composition(order: int, df: str) -> str:
    if df in {"hook", "action"}:
        return "center-subject"
    if df == "sensory":
        return "three-layer-depth" if order % 2 == 0 else "foreground-background"
    if df == "approach":
        return "two-character-stack" if order % 2 == 0 else "center-subject"
    return "center-subject"


def _camera_axis(df: str, idx: int) -> str:
    axes = {
        "hook": "dolly_in",
        "approach": "pan_with",
        "sensory": "low_lean",
        "reaction": "ecu_hold",
        "action": "dolly_in",
        "afterglow": "pull_back",
        "bridge": "locked",
    }
    base = axes.get(df, "dolly_in")
    if idx % 3 == 1 and base == "dolly_in":
        return "ecu_hold"
    return base


def _motion_text(axis: str) -> str:
    """Compile a camera label into a playable camera/body instruction."""
    return {
        "dolly_in": "slow dolly in as the body commits to the action",
        "pan_with": "camera pans with the character's movement",
        "low_lean": "low-angle lean in with a visible weight shift",
        "ecu_hold": "locked close-up with breathing and an eye shift",
        "pull_back": "slow pull back as the result settles",
        "locked": "locked frame with a small observable body shift",
    }.get(axis, "restrained camera move with a visible body shift")


def _production_mode(df: str, shot_role: str) -> str:
    if shot_role == "env":
        return "text-to-video"
    if df in {"bridge", "afterglow"}:
        return "panel-animation"
    if df in {"action", "sensory", "hook"}:
        return "single-keyframe-i2v"
    return "single-keyframe-i2v"


def plan_shots(
    beat: dict[str, Any],
    *,
    scene: dict[str, Any],
    shot_counter_start: int,
    character_ids: list[str],
    location_id: str | None,
    chain_continue: bool = True,
    episode_number: int = 1,
) -> list[dict[str, Any]]:
    """shot.plan — expand beat into 1–N vertical shots."""
    n = max(1, min(3, int(beat.get("shots_n") or 1)))
    budget = float(beat.get("targetDuration") or 6)
    per_floor = max(3.0, round(budget / n, 1))
    df = str(beat.get("dramatic_function") or "action")
    if df not in DRAMATIC_FUNCS:
        df = "action"
    source = str(beat.get("source_text") or beat.get("action") or "")
    sents = _sentences(source) or [source]

    shots: list[dict[str, Any]] = []
    coverage_roles_by_beat = {
        "hook": ["establish"],
        "approach": ["context"],
        "sensory": ["action", "reveal"],
        "action": ["decision", "reaction"],
        "afterglow": ["consequence"],
        "bridge": ["context"],
    }
    coverage_roles = coverage_roles_by_beat.get(df, ["action"])
    used_nars: set[str] = set()
    for i in range(n):
        idx = shot_counter_start + i
        scene_order = int(scene.get("order") or 1)
        beat_order = int(beat.get("order") or 1)
        sid = f"ep{episode_number:02d}_sc{scene_order:02d}_bt{beat_order:02d}_sh{i + 1:02d}"
        piece = sents[i] if i < len(sents) else sents[-1]
        # second shot in beat: reaction / insert flavor
        local_df = df
        if n > 1 and i == n - 1 and df in {"sensory", "action"}:
            local_df = "reaction"
        shot_role = "hero"
        if local_df == "bridge":
            shot_role = "env"
        chain = "continue" if chain_continue and idx > 1 else ("continue" if idx > 1 else "cut")
        if i == 0 and idx == 1:
            chain = "cut"
        panel_id = f"panel_{sid}_01"
        prod = _production_mode(local_df, shot_role)
        vc = _vertical_composition(idx, local_df)
        axis = _camera_axis(local_df, idx)
        coverage_role = coverage_roles[i % len(coverage_roles)]
        heat_phase = str(beat.get("heat_phase") or "").strip().lower() or ""
        coitus_beat = str(beat.get("coitus_beat") or "").strip().lower() or ""
        wardrobe_state = str(beat.get("wardrobe_state") or "full").strip().lower() or "full"
        # 定器特写: lock / insert plates pin coverage_role=detail (impact + detail CU gate)
        if coitus_beat == "lock" or (coitus_beat == "rhythm" and i > 0):
            coverage_role = "detail"
        # Explicit four-beat sex arc (plan-time pin · 2026-07-29)
        sex_arc_beat = ""
        if heat_phase == "climax" or coitus_beat == "finish":
            sex_arc_beat = "climax_release"
        elif heat_phase == "afterglow" or coitus_beat == "hook":
            sex_arc_beat = "afterglow"
        elif heat_phase == "act" or coitus_beat in {"union", "rhythm", "lock"}:
            sex_arc_beat = "penetration"
        elif coitus_beat == "entry" and heat_phase in {"foreplay", "act"}:
            sex_arc_beat = "entry"
        elif heat_phase == "foreplay" or coitus_beat == "undress":
            sex_arc_beat = "foreplay"
        # Cinema-grade camera prompt (Seedance camera language bridge, 2026-07-23).
        # Enriches the fixed-enum axis with structured move/shot/angle/pacing/lighting.
        from cinema_prompt import build_camera_prompt as _build_cinema_prompt

        scene_type = str(scene.get("genre") or "").strip().lower() or None
        cinema = _build_cinema_prompt(
            dramatic_function=local_df,
            shot_index=idx,
            heat_phase=heat_phase or None,
            scene_type=scene_type,
            duration_sec=float(beat.get("duration_sec") or 5.0),
        )
        camera_prompt = cinema["camera_prompt"]
        # Adult: coitus-readable action — but keep user text in must_show when present
        adult_actions = {
            "entry": "pin partner entry mount-settle weight drop pelvis aim",
            "undress": "removes dress armor straps slide undress bare shoulders",
            "union": "straddle-seat hips settle pelvis-lock skin-to-skin",
            "rhythm": "hips-sink grind-forward thrust-rhythm twice clutch fabric",
            "lock": "leg-wrap-waist clutch sheets micro-tremor lock",
            "finish": "arch-finish residual-tremor wet eyes body softens",
            "hook": "ear whisper residual hold next round invitation",
        }
        user_piece = str(piece or "").strip()
        if coitus_beat in adult_actions:
            # VO-visual align: action mirrors user verbs when user wrote them
            must_show = adult_actions[coitus_beat]
            from story_plan import _user_nar_substantive  # lazy (circular-safe)

            if _user_nar_substantive(user_piece):
                must_show = f"{must_show}; story: {_clip_nar(user_piece, 40)}"
            visible_change = must_show
            action_text = must_show
        else:
            must_show = f"{coverage_role}: {_clip_nar(user_piece, 60)}"
            visible_change = {
                "establish": "空间与人物关系可读",
                "context": "人物目标与阻力进入画面",
                "reveal": "新线索或欲望被看见",
                "reaction": "角色反应发生变化",
                "action": "冲突动作完成一步",
                "decision": "角色做出不可撤回的选择",
                "consequence": "动作造成的状态后果",
            }[coverage_role]
            action_text = must_show
        extreme_seed = bool(beat.get("_extreme_seed"))
        # P0 user-source fidelity: never wholesale replace user nar with 展厅模板
        from story_plan import preserve_user_nar  # lazy (circular-safe)

        nar = preserve_user_nar(
            user_piece,
            heat_phase=heat_phase,
            coitus_beat=coitus_beat
            if not (coitus_beat == "rhythm" and i > 0)
            else ("rhythm" if i == 0 else "rhythm"),
            extreme_seed=extreme_seed,
            max_chars=48,
        )
        if coitus_beat == "rhythm" and i > 0 and not _user_nar_substantive(user_piece):
            from story_plan import preserve_user_nar as _preserve

            nar = _preserve(
                "",
                heat_phase=heat_phase,
                coitus_beat="rhythm",
                extreme_seed=extreme_seed,
                max_chars=48,
            )
            if extreme_seed:
                nar = _clip_nar("换姿再沉腰。夹紧，不许退。", 48)
            else:
                nar = _clip_nar("再沉腰。节奏是她给的。", 48)
        if coitus_beat == "entry" and heat_phase == "foreplay":
            nar = _clip_nar(f"{nar.rstrip('。')}。呼吸更近。", 48)
        if nar in used_nars:
            progression = {
                "foreplay": "呼吸更近。",
                "act": "动作推进。",
                "climax": "情绪抵达。",
                "afterglow": "余温未散。",
            }.get(heat_phase, "画面推进。")
            nar = _clip_nar(f"{nar.rstrip('。')}。{progression}", 48)
        used_nars.add(nar)
        # Multi-pose: rotate sex_pose by coitus beat + index
        pose_cycle = {
            "entry": "wall_pin",
            "undress": "lap_grind",
            "union": "straddle",
            "rhythm": "cowgirl" if i == 0 else "from_behind",
            "lock": "lotus",
            "finish": "missionary_pin",
            "hook": "side_entry",
        }
        sex_pose = pose_cycle.get(coitus_beat) or ""
        # Act/climax plates: longer floor so sex duration ratio hits ≥20%/40%
        floor = per_floor
        if heat_phase in {"act", "climax"}:
            floor = max(per_floor, 8.0)
        elif heat_phase == "foreplay":
            floor = max(per_floor, 5.0)
        per = _duration_for_nar(nar, floor=floor)
        # Size ladder: setup wide → act medium → climax CU → lock insert
        # Size ladder pressure: avoid 3× same rank in a row (SIZE_STACK_FLAT)
        if coitus_beat == "entry" and heat_phase == "setup":
            shot_size = "medium full"
        elif coitus_beat == "undress":
            shot_size = "medium"
        elif coitus_beat == "entry":
            shot_size = "close-up"  # foreplay pressure
        elif coitus_beat == "union":
            shot_size = "medium"
        elif coitus_beat == "rhythm":
            shot_size = "medium" if i == 0 else "close-up"
        elif coitus_beat == "lock":
            shot_size = "close-up insert fabric hands"
        elif coitus_beat == "finish":
            shot_size = "close-up"
        elif coitus_beat == "hook":
            shot_size = "medium"
        else:
            shot_size = "close-up" if local_df in {"hook", "reaction", "action"} else "medium"
        motion_by_cb = {
            "entry": "pin seat weight drop mount-settle camera push-in torso lean",
            "undress": "straps slide dress peels bare skin expands shoulders lean",
            "union": "straddle-seat hips settle pelvis-lock weight down heavy breath",
            "rhythm": "hips-sink twice grind-forward thrust-rhythm locked camera",
            "lock": "leg-wrap-waist clutch sheets micro-tremor shoulders tremble",
            "finish": "arch-finish residual-tremor static hold heavy breath",
            "hook": "lean to ear residual pull-back hold",
        }
        motion = motion_by_cb.get(coitus_beat) or _motion_text(axis)
        char_ids = list(character_ids[:2]) or ["hero"]
        subject = f"vertical 9:16, adult {char_ids[0] if char_ids else 'hero'}"
        if wardrobe_state in {"partial", "undressed", "bare"}:
            subject += f" {wardrobe_state} bare skin readable"
        # Derive multi-axis character states (hair, skin, arousal, wardrobe)
        c_hair = "neat"
        c_skin = "normal"
        c_arousal = "calm"
        if heat_phase in {"act", "climax"}:
            c_hair = "disheveled"
            c_skin = "glistening_sweat"
            c_arousal = "climax_ecstasy" if heat_phase == "climax" else "heavy_breathing"
        elif heat_phase == "foreplay":
            c_hair = "slightly_moussed"
            c_skin = "flushed"
            c_arousal = "heavy_breathing"
        elif heat_phase == "afterglow":
            c_hair = "sweat_moistened_strands"
            c_skin = "afterglow_blush"
            c_arousal = "calm"
        character_states = {
            "wardrobe": wardrobe_state,
            "hair": c_hair,
            "skin": c_skin,
            "arousal": c_arousal,
        }

        film_dsl: dict[str, Any] = {
            "subject": subject,
            "action": action_text,
            "motion": motion,
            "camera_axis": axis,
            "camera_prompt": camera_prompt,
            "visible_change": visible_change,
            "story_beat": str(beat.get("objective") or local_df),
            "start_pose": (
                f"already {wardrobe_state} from prior undress"
                if wardrobe_state in {"partial", "undressed", "bare"}
                else "enter beat"
            ),
            "end_pose": "exit beat — feeds next",
            "chain_mode": chain,
            "cut_on": "mid_motion" if chain == "continue" else "fresh",
            "cast": char_ids,
            "viewpoint": "objective",
            "look_axis": "center",
            "camera": {
                "shot_size": shot_size,
                "angle": "slight low"
                if coitus_beat in {"union", "rhythm", "entry"}
                else "eye_level",
            },
            "wardrobe_state": wardrobe_state,
            "character_states": character_states,
        }
        if heat_phase:
            film_dsl["heat_phase"] = heat_phase
        if coitus_beat:
            film_dsl["coitus_beat"] = coitus_beat
        if sex_arc_beat:
            film_dsl["sex_arc_beat"] = sex_arc_beat
        if sex_pose:
            film_dsl["sex_pose"] = sex_pose
        shots.append(
            {
                "id": sid,
                "order": idx,
                "filmSpecShotId": sid,
                "beatId": beat["id"],
                "beat_id": beat["id"],
                "narrativePurpose": str(beat.get("objective") or local_df),
                "dramaticFunction": local_df,
                "shotSize": shot_size,
                "verticalComposition": vc,
                "cameraMovement": axis,
                "productionMode": prod,
                "targetDuration": per,
                "characterIds": char_ids,
                "locationId": location_id,
                "wardrobeState": wardrobe_state,
                "characterStates": character_states,
                "character_states": character_states,
                "heatPhase": heat_phase,
                "coitusBeat": coitus_beat,
                "sexArcBeat": sex_arc_beat,
                "sexPose": sex_pose,
                "chainMode": chain,
                "coverage_role": coverage_role,
                "must_show": must_show,
                "visible_change": visible_change,
                "start_state": AUTHORING_PLACEHOLDER,
                "end_state": AUTHORING_PLACEHOLDER,
                "playable_action": action_text if coitus_beat else AUTHORING_PLACEHOLDER,
                "expectation": AUTHORING_PLACEHOLDER,
                "subtext": AUTHORING_PLACEHOLDER,
                "gaze_target": AUTHORING_PLACEHOLDER,
                "reaction_trigger": AUTHORING_PLACEHOLDER,
                "body_state": wardrobe_state,
                "source_refs": [beat.get("id")],
                "nar": nar,
                "panelIds": [panel_id],
                "keyframeIds": [],
                "motionClipIds": [],
                "dialogueLineIds": [f"dlg_{sid}"],
                "panels": [
                    {
                        "id": panel_id,
                        "order": 1,
                        "subject": char_ids[0] if char_ids else "hero",
                        "action": must_show,
                        "expression": AUTHORING_PLACEHOLDER,
                        "location": location_id or "",
                        "verticalComposition": vc,
                        "cameraAngle": "eye_level",
                        "lighting": "",
                        "style": "vertical drama comic",
                        "continuityConstraints": [f"chain_mode={chain}"],
                        "negativeConstraints": [
                            "no landscape crop",
                            "no horizontal storyboard paste",
                        ],
                        "referenceAssetIds": [],
                        "sourcePromptPath": None,
                        "must_include": [must_show],
                        "playable_action": AUTHORING_PLACEHOLDER,
                        "gaze_target": AUTHORING_PLACEHOLDER,
                    }
                ],
                "assetHints": {
                    "keyframePath": None,
                    "clipPath": None,
                    "promptPath": None,
                    "hasKeyframe": False,
                    "hasClip": False,
                    "hasPrompt": False,
                },
                "_film": {
                    "title": _clip_nar(str(beat.get("objective") or sid), 24),
                    "shot_role": shot_role,
                    "dramatic_function": local_df,
                    "duration_sec": per,
                    "nar": nar,
                    "beat_id": beat["id"],
                    "heat_phase": heat_phase or None,
                    "coitus_beat": coitus_beat or None,
                    "sex_arc_beat": sex_arc_beat or None,
                    "sex_pose": sex_pose or None,
                    "wardrobe_state": wardrobe_state,
                    "dsl": film_dsl,
                },
            }
        )
    return shots

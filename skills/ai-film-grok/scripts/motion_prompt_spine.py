#!/usr/bin/env python3
"""Motion Prompt Spine — film core → motion generation (Grok + H3 shared).

Order (author-facing prompt body):
  dramatic_function → want_beat → action/motion/visible_change
  → camera_prompt → dialogue/foley audio → (provider prefix separate)

Fail-closed rules live in ``assert_motion_prompt_core``.

MiniMax H3 temporal prompt builder (5090 H3 primary path):
``build_h3_temporal_prompt()`` produces ``[Xs-Ys]`` segmented prompts
that match the H3 DiT temporal decomposition format.
"""

from __future__ import annotations

import os
from typing import Any


class MotionCoreError(ValueError):
    """Raised when a motion prompt is missing film-core payload."""


# Shared DF / heat sets — single source for spine prompts + optical gate.
MEAT_PHASES = frozenset({"act", "climax"})
_HIGH_HEAT = frozenset({"act", "climax", "peak"})  # thrash inject; not afterglow
_HIGH_DF = frozenset({"action", "climax", "hook", "impact", "peak"})
_SOFT_DF = frozenset({"reaction", "afterglow", "bridge", "insert", "sensory"})
_BARE_WARDROBE = frozenset({"bare", "undressed", "nude"})
_PROMPT_TIERS = frozenset({"soft", "medium", "high"})
_OPTICAL_TIERS = frozenset({"soft", "medium", "normal", "meat", "high"})


def motion_core_skip_enabled() -> bool:
    """Escape hatch for legacy films / emergency bulk (AIFILM_SKIP_MOTION_CORE=1)."""
    return os.environ.get("AIFILM_SKIP_MOTION_CORE", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def motion_tier_resolve(
    shot: dict[str, Any] | None = None,
    *,
    heat_phase: str | None = None,
    dramatic_function: str | None = None,
    spine_tier: str | None = None,
    wardrobe_state: str | None = None,
    spoken_dialogue: bool | None = None,
    screen_mode: str | None = None,
) -> dict[str, Any]:
    """Single tier truth for prompts + pixel gate (Phase A · 2026-08-04).

    Returns:
      prompt_tier: soft | medium | high  (language for motion prompts)
      optical_tier: soft | medium | normal | meat | high  (mean floors)
    """
    sh = shot if isinstance(shot, dict) else {}
    heat = str(heat_phase if heat_phase is not None else heat_phase_of(sh)).strip().lower()
    df = (
        str(dramatic_function if dramatic_function is not None else dramatic_function_of(sh))
        .strip()
        .lower()
    )
    wardrobe = (
        str(wardrobe_state if wardrobe_state is not None else (sh.get("wardrobe_state") or ""))
        .strip()
        .lower()
    )
    spine = str(spine_tier or "").strip().lower()
    has_dlg = bool(spoken_dialogue_text(sh)) if spoken_dialogue is None else bool(spoken_dialogue)
    screen = shot_screen_mode(sh) if screen_mode is None else str(screen_mode or "").strip()

    optical = "normal"
    # 1) Meat heat never demoted by soft DF tags
    if heat in MEAT_PHASES:
        optical = "meat"
    # 2) Afterglow recovery: medium floor (not thrash)
    elif heat == "afterglow" or df == "afterglow":
        optical = "medium"
    # 3) Bare wardrobe: meat unless soft/afterglow recovery
    elif wardrobe in _BARE_WARDROBE:
        optical = "medium" if df in _SOFT_DF else "meat"
    # 4) High DF
    elif df in _HIGH_DF:
        optical = "meat" if df in {"action", "climax", "impact", "peak"} else "high"
    # 5) Soft DF
    elif df in _SOFT_DF:
        optical = "soft"
    # 6) Explicit spine/prompt tier already on the row
    elif spine in _OPTICAL_TIERS:
        optical = "meat" if spine == "high" else spine
    elif spine in _PROMPT_TIERS:
        optical = {"soft": "soft", "medium": "medium", "high": "meat"}[spine]
    # 7) On-camera dialogue micro-performance
    elif has_dlg and screen in {"on_camera", ""} or heat in {"foreplay", "build"}:
        optical = "medium"
    else:
        optical = "normal"

    if optical not in _OPTICAL_TIERS:
        optical = "normal"

    prompt_map = {
        "soft": "soft",
        "medium": "medium",
        "normal": "medium",
        "meat": "high",
        "high": "high",
    }
    prompt_tier = prompt_map.get(optical, "medium")
    return {
        "prompt_tier": prompt_tier,
        "optical_tier": optical,
        "dramatic_function": df or None,
        "heat_phase": heat or None,
        "wardrobe_state": wardrobe or None,
    }


def motion_tier_for(shot: dict[str, Any]) -> str:
    """soft | medium | high — prompt-language tier (delegates to motion_tier_resolve)."""
    return str(motion_tier_resolve(shot)["prompt_tier"])


def spoken_dialogue_text(shot: dict[str, Any]) -> str:
    cues = shot.get("audio_cues")
    if not isinstance(cues, list):
        return ""
    for cue in cues:
        if not isinstance(cue, dict):
            continue
        if (
            cue.get("kind") == "voice"
            and cue.get("line_type") == "dialogue"
            and str(cue.get("spoken_text") or "").strip()
        ):
            return str(cue["spoken_text"]).strip()
    return ""


def shot_screen_mode(shot: dict[str, Any]) -> str:
    mode = str(shot.get("screen_mode") or "").strip()
    if mode:
        return mode
    cues = shot.get("audio_cues")
    if not isinstance(cues, list):
        return ""
    for cue in cues:
        if not isinstance(cue, dict):
            continue
        if (
            cue.get("kind") == "voice"
            and cue.get("line_type") == "dialogue"
            and str(cue.get("spoken_text") or "").strip()
        ):
            return str(cue.get("screen_mode") or "").strip()
    return ""


def dramatic_function_of(shot: dict[str, Any]) -> str:
    raw = shot.get("dramatic_function")
    if raw:
        return str(raw).strip().lower()
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    return str(dsl.get("dramatic_function") or "").strip().lower()


def heat_phase_of(shot: dict[str, Any]) -> str:
    return str(shot.get("heat_phase") or "").strip().lower()


def _short(text: str, n: int = 80) -> str:
    t = " ".join(str(text or "").split())
    if len(t) <= n:
        return t
    return t[: n - 1].rstrip() + "…"


def want_beat_line(spec: dict[str, Any] | None, shot: dict[str, Any]) -> str:
    """One short line: how this beat advances protagonist want / theme."""
    di = {}
    if isinstance(spec, dict):
        raw = spec.get("director_intent")
        if isinstance(raw, dict):
            di = raw
    want = (
        str(di.get("protagonist_want") or "").strip()
        or str(di.get("want") or "").strip()
        or str(di.get("theme") or "").strip()
        or str(di.get("central_conflict") or "").strip()
    )
    df = dramatic_function_of(shot) or "beat"
    if want:
        return f"This beat advances want ({df}): {_short(want, 72)}"
    if df and df not in {"", "bridge"}:
        return f"Dramatic function: {df}"
    return ""


def dsl_action_parts(shot: dict[str, Any]) -> list[str]:
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    parts: list[str] = []
    for key in ("action", "motion", "visible_change"):
        val = str(dsl.get(key) or "").strip()
        if val and val.lower() not in {"needs_authoring", "tbd", "todo", "n/a"}:
            parts.append(val)
    try:
        from content_channels import visual_prompt_action

        v_act = visual_prompt_action(shot)
        if v_act and v_act not in parts:
            parts.append(v_act)
    except Exception:
        nar = str(shot.get("nar") or "").strip()
        if not parts and nar and len(nar) <= 120:
            parts.append(nar)
    return parts


# DP optics matrix (hard-defaults / dp-optics): shot_size → prime mm phrase.
# Author lens_mm / camera_prompt with "mm" always wins over auto inject.
_SHOT_SIZE_FOCAL: dict[str, tuple[int, str]] = {
    "wide": (35, "35mm wide establishing plate"),
    "ws": (35, "35mm wide establishing plate"),
    "w": (35, "35mm wide establishing plate"),
    "full": (35, "35mm full-body readable plate"),
    "fs": (35, "35mm full-body readable plate"),
    "long": (35, "35mm long shot"),
    "ls": (35, "35mm long shot"),
    "ms": (50, "50mm medium two-shot / torso"),
    "medium": (50, "50mm medium two-shot / torso"),
    "m": (50, "50mm medium two-shot / torso"),
    "mcu": (50, "50mm medium close-up"),
    "medium_close": (50, "50mm medium close-up"),
    "cu": (85, "85mm close-up face/reaction"),
    "close": (85, "85mm close-up face/reaction"),
    "closeup": (85, "85mm close-up face/reaction"),
    "close_up": (85, "85mm close-up face/reaction"),
    "close-up": (85, "85mm close-up face/reaction"),
    "ecu": (105, "105mm extreme close-up / macro insert"),
    "extreme_close": (105, "105mm extreme close-up / macro insert"),
    "extreme_closeup": (105, "105mm extreme close-up / macro insert"),
    "insert": (105, "105mm insert / L4 detail"),
    "l4": (105, "105mm insert / L4 detail"),
    "insert_l4": (105, "105mm insert / L4 detail"),
    "macro": (105, "105mm macro insert"),
}


def shot_size_of(shot: dict[str, Any]) -> str:
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    cam = dsl.get("camera") if isinstance(dsl.get("camera"), dict) else {}
    raw = (
        shot.get("shot_size")
        or cam.get("shot_size")
        or dsl.get("shot_size")
        or shot.get("framing")
        or dsl.get("framing")
        or ""
    )
    return str(raw).strip().lower().replace(" ", "_")


def focal_clause(shot: dict[str, Any]) -> str:
    """One-line DP lens inject (go5 · 2.37.2). Skip if author already set lens."""
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    cam = dsl.get("camera") if isinstance(dsl.get("camera"), dict) else {}
    # Author explicit lens
    for key in ("lens_mm", "focal_length", "focal_mm"):
        for src in (dsl, cam, shot):
            if not isinstance(src, dict):
                continue
            val = src.get(key)
            if val is None or val == "":
                continue
            try:
                mm = int(float(val))
            except (TypeError, ValueError):
                mm = None
            if mm:
                return f"Lens: {mm}mm cinematic prime (author lock)."
    author_cam = str(dsl.get("camera_prompt") or cam.get("prompt") or "").lower()
    if "mm" in author_cam and any(ch.isdigit() for ch in author_cam):
        return ""  # already in camera_prompt
    size = shot_size_of(shot)
    if not size:
        return ""
    # normalize common tokens
    token = size.split("/")[0].split(",")[0].strip()
    hit = _SHOT_SIZE_FOCAL.get(token)
    if not hit:
        # partial match e.g. medium_full → medium family
        for key, pair in _SHOT_SIZE_FOCAL.items():
            if key in token or token in key:
                hit = pair
                break
    if not hit:
        return ""
    mm, phrase = hit
    return f"Lens: {mm}mm ({phrase})."


def camera_clause(shot: dict[str, Any]) -> str:
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    cam = str(dsl.get("camera_prompt") or "").strip()
    focal = focal_clause(shot)
    if cam:
        # Append focal only if not already implied
        if focal and "mm" not in cam.lower():
            return f"{cam} {focal}".strip()
        return cam
    framing = str(shot.get("framing") or dsl.get("framing") or "").strip()
    parts: list[str] = []
    if framing:
        parts.append(f"Framing: {framing}")
    if focal:
        parts.append(focal)
    return " ".join(parts).strip()


def audio_clause(shot: dict[str, Any]) -> str:
    dialogue = spoken_dialogue_text(shot)
    screen = shot_screen_mode(shot)
    if dialogue and screen == "off_camera":
        return (
            f"Audio: the character continues this line off camera while the picture "
            f"holds the reverse or coverage shot; spoken in natural Mandarin; "
            f"line: 「{dialogue}」."
        )
    if dialogue:
        return (
            f"Audio: the visible character speaks this line in natural Mandarin on camera; "
            f"mouth visibly articulates the line, lip sync priority; line: 「{dialogue}」."
        )
    tier = motion_tier_for(shot)
    if tier == "high":
        return (
            "Audio: energetic diegetic ambience and fabric/foley matched to the action; "
            "no on-screen speech unless the shot is clearly dialogue."
        )
    return (
        "Audio: natural diegetic ambience and soft foley matched to the action; "
        "no on-screen speech unless the shot is clearly dialogue."
    )


def core_fields(spec: dict[str, Any] | None, shot: dict[str, Any]) -> dict[str, Any]:
    """Machine-readable core payload for shot intent / receipts."""
    dialogue = spoken_dialogue_text(shot)
    df = dramatic_function_of(shot)
    heat = heat_phase_of(shot)
    actions = dsl_action_parts(shot)
    resolved = motion_tier_resolve(shot)
    return {
        "dramatic_function": df or None,
        "heat_phase": heat or None,
        "want_beat": want_beat_line(spec, shot) or None,
        "motion_tier": resolved["prompt_tier"],
        "optical_tier": resolved["optical_tier"],
        "spoken_text": dialogue or None,
        "screen_mode": shot_screen_mode(shot) or None,
        "speaker": str(shot.get("speaker") or "").strip() or None,
        "has_action_core": bool(actions) or bool(dialogue),
        "action_summary": ". ".join(actions) if actions else None,
        "camera_prompt": camera_clause(shot) or None,
        "focal_clause": focal_clause(shot) or None,
        "shot_size": shot_size_of(shot) or None,
        "continuity_required": str(
            (shot.get("dsl") or {}).get("chain_mode") if isinstance(shot.get("dsl"), dict) else ""
        ).lower()
        == "continue"
        or bool(shot.get("parent_shot_id")),
    }


def motion_core_clauses(
    spec: dict[str, Any] | None,
    shot: dict[str, Any],
    *,
    include_audio: bool = True,
) -> list[str]:
    """Ordered semantic clauses (no provider geometry prefix)."""
    clauses: list[str] = []
    df = dramatic_function_of(shot)
    if df:
        clauses.append(f"Dramatic function: {df}")
    want = want_beat_line(spec, shot)
    if want:
        clauses.append(want)
    tier = motion_tier_for(shot)
    if tier == "high":
        clauses.append(
            "HIGH MOTION priority: large visible pose/body change; "
            "avoid frozen portrait or micro-breath-only."
        )
    elif tier == "soft":
        clauses.append(
            "SOFT MOTION: micro-performance only (eyes, breath, jaw); locked camera preferred."
        )
    actions = dsl_action_parts(shot)
    if actions:
        clauses.append(". ".join(actions))
    cam = camera_clause(shot)
    if cam:
        clauses.append(cam)
    if include_audio:
        clauses.append(audio_clause(shot))
    return [c for c in clauses if c and str(c).strip()]


def provider_prefix(mode: str) -> str:
    m = (mode or "i2v").strip().lower()
    if m == "r2v":
        return (
            "Vertical 9:16. Use <Picture 1> as identity and style reference. "
            "Keep identity and wardrobe fixed."
        )
    if m == "t2v":
        return "Vertical 9:16 text-to-video plate."
    if m in {"flf", "first_last", "first_last_frame", "i2v_flf"}:
        return (
            "Vertical 9:16. First-last-frame image-to-video with medium cel-anime style lock. "
            "Animate from the first keyframe toward the last keyframe; land on the last pose "
            "and wardrobe; keep identity fixed."
        )
    return (
        "Vertical 9:16. Animate the start frame with medium cel-anime style lock. "
        "Keep identity and wardrobe fixed."
    )


def build_motion_prompt(
    spec: dict[str, Any] | None,
    shot: dict[str, Any],
    *,
    mode: str = "i2v",
    include_provider_prefix: bool = True,
) -> str:
    """Full motion prompt for H3 (or Grok body) when no author file."""
    body = " ".join(motion_core_clauses(spec, shot, include_audio=True)).strip()
    # No silent "subtle push-in" pad — empty body must fail assert_motion_prompt_core
    # (camera motion only serves in-world visible_change, never PPT push-in alone).
    if not body:
        body = ""
    # F2 · story beat prefix (source_quote / playable_action)
    try:
        from input_fidelity import inject_story_beat_into_prompt

        body = inject_story_beat_into_prompt(body, shot)
    except Exception:
        pass
    if include_provider_prefix:
        return f"{provider_prefix(mode)} {body}".strip()
    return body


# ── MiniMax H3 temporal prompt builder (5090 H3 primary path) ──────────────

_H3_SEGMENT_DURATIONS = {
    # duration_sec → segment count (~2–3s per clear action)
    5: 2,
    6: 2,
    7: 3,
    8: 3,
    9: 3,
    10: 4,
    11: 4,
    12: 4,
    13: 5,
    14: 5,
    15: 5,
}


def _h3_segment_count(duration_sec: float, *, prompt_tier: str = "medium") -> int:
    """Return temporal segment count for duration (+ soft/high density nudge)."""
    dur = int(round(duration_sec))
    if dur <= 5:
        base = 2
    elif dur >= 15:
        base = 5
    else:
        base = _H3_SEGMENT_DURATIONS.get(dur, 3)
    tier = (prompt_tier or "medium").strip().lower()
    if tier == "soft":
        return max(2, base - (1 if base > 2 else 0))
    if tier == "high" and dur >= 8:
        cap = 3 if dur <= 5 else (4 if dur <= 8 else (5 if dur <= 10 else 8))
        return min(cap, base + 1)
    return base


def build_h3_temporal_prompt(
    spec: dict[str, Any] | None,
    shot: dict[str, Any],
    *,
    mode: str = "i2v",
    duration_sec: float | None = None,
    ref_image_paths: list[str] | None = None,
) -> str:
    """Build MiniMax H3 Layer-4 timed action script for 5090 generation.

    Output (no Vertical 9:16 prefix — H3 is natively 9:16)::

      [0s-2s] continuity + open + primary action + camera + env + mood ...
      [2s-5s] ...
      [5s-8s] ... ending pose
      Audio: ...

    When 2V + reference images available, injects the Grok reference
    composition stage before the timeline segments (see h3_timeline_prompt).

    Controls: temporal decomposition, one primary action/segment,
    subject+camera+env motion, continuity anchors, continuous vs multi-cut,
    implied diegetic sound + dialogue inject. See ``h3_timeline_prompt``.
    """
    from h3_timeline_prompt import (
        build_segment_lines,
        inject_2v_reference_stage,
        resolve_duration_sec,
    )

    if duration_sec is None:
        h3 = (spec or {}).get("h3") if isinstance(spec, dict) else {}
        h3 = h3 if isinstance(h3, dict) else {}
        duration_sec = resolve_duration_sec(
            shot, default=float(h3.get("max_duration_sec") or 8)
        )
    duration_sec = max(3.0, min(float(duration_sec), 15.0))

    tier = motion_tier_for(shot)
    n = _h3_segment_count(duration_sec, prompt_tier=tier)
    shot_x = dict(shot) if isinstance(shot, dict) else {}
    shot_x["h3_mode"] = mode

    has_dlg = bool(spoken_dialogue_text(shot))
    # Dialogue performance: denser mouth language, never body HIGH MOTION thrash.
    eff_tier = "medium" if has_dlg and tier == "high" else tier
    if has_dlg:
        n = _h3_segment_count(duration_sec, prompt_tier=eff_tier)

    segs = build_segment_lines(
        spec,
        shot_x,
        duration_sec=duration_sec,
        prompt_tier=eff_tier,
        n_segments=n,
        inject_continuity_in_first=True,
    )
    if segs:
        lead: list[str] = []
        df = dramatic_function_of(shot)
        if df and df not in {"beat", "setup"}:
            lead.append(f"Dramatic function: {df}")
        want = want_beat_line(spec, shot)
        if want and not has_dlg:
            lead.append(want.rstrip("."))
        if has_dlg:
            lead.append(
                "MOUTH ENERGY priority: clear jaw open-close each Mandarin syllable; "
                "visible lip sync; keep face identity fixed; never freeze the mouth"
            )
        elif tier == "high":
            lead.append(
                "HIGH MOTION priority: large visible pose/body change across the timeline"
            )
        elif tier == "soft":
            lead.append("SOFT MOTION: micro-performance only; locked camera preferred")
        if lead:
            tc, _, rest = segs[0].partition("] ")
            segs[0] = f"{tc}] {'; '.join(lead)}. {rest}".strip()

    try:
        from input_fidelity import inject_story_beat_into_prompt

        joined = inject_story_beat_into_prompt("\n".join(segs), shot)
        segs = joined.split("\n")
    except Exception:
        pass

    # Inject 2V reference stage when reference images are available.
    if ref_image_paths:
        body = "\n".join(segs)
        body = inject_2v_reference_stage(
            body, shot, ref_image_paths=ref_image_paths, mode=mode
        )
        segs = body.split("\n")

    audio = audio_clause(shot)
    body = "\n".join(segs)
    if audio:
        body = f"{body}\n{audio}"
    return body.strip()


# ── end H3 temporal builder ────────────────────────────────────────────────


def ensure_motion_core_in_prompt(
    text: str,
    spec: dict[str, Any] | None,
    shot: dict[str, Any],
    *,
    timeline: bool | None = None,
    duration_sec: float | None = None,
) -> str:
    """Merge missing core clauses into an author prompt (idempotent).

    When ``timeline=True`` and author text has no ``[0s-…]`` markers, append
    Layer-4 continuity + timed segments (5090 H3 path).
    """
    base = (text or "").strip()
    if not base:
        if timeline:
            return build_h3_temporal_prompt(
                spec, shot, mode="i2v", duration_sec=duration_sec
            )
        return build_motion_prompt(spec, shot, mode="i2v", include_provider_prefix=False)

    out = base
    try:
        from input_fidelity import inject_story_beat_into_prompt

        out = inject_story_beat_into_prompt(out, shot)
    except Exception:
        pass
    df = dramatic_function_of(shot)
    if (
        df
        and f"Dramatic function: {df}" not in out
        and f"dramatic function: {df}" not in out.lower()
    ):
        out = f"Dramatic function: {df}. {out}"

    want = want_beat_line(spec, shot)
    if want and want not in out and "advances want" not in out.lower():
        out = f"{out.rstrip()} {want}"

    tier = motion_tier_for(shot)
    if tier == "high" and "HIGH MOTION" not in out.upper():
        heat = heat_phase_of(shot)
        if heat in _HIGH_HEAT or heat in MEAT_PHASES or dramatic_function_of(shot) in _HIGH_DF:
            out = f"{out.rstrip()} HIGH MOTION priority: large visible body/pose change."

    cam = camera_clause(shot)
    if cam and cam not in out:
        out = f"{out.rstrip()} {cam}"

    dialogue = spoken_dialogue_text(shot)
    audio = audio_clause(shot)
    if dialogue:
        if dialogue not in out or "lip sync" not in out.lower():
            out = f"{out.rstrip()} {audio}"
    elif "Audio:" not in out:
        out = f"{out.rstrip()} {audio}"

    if timeline:
        try:
            from h3_timeline_prompt import has_timeline_markers, merge_timeline_into_author

            if not has_timeline_markers(out):
                out = merge_timeline_into_author(
                    out, spec, shot, duration_sec=duration_sec
                )
        except Exception:
            pass

    return out.strip()


def assert_motion_prompt_core(
    prompt: str,
    shot: dict[str, Any],
    *,
    mode: str = "i2v",
    role: str | None = None,
) -> dict[str, Any]:
    """Fail closed when motion prompt cannot carry film core.

    Returns a small audit dict when ok.
    """
    text = (prompt or "").strip()
    role_n = (role or str(shot.get("shot_role") or "hero")).strip().lower()
    mode_n = (mode or "i2v").strip().lower()
    actions = dsl_action_parts(shot)
    dialogue = spoken_dialogue_text(shot)
    compact = " ".join(text.split())

    if len(compact) < 32:
        raise MotionCoreError(
            f"MOTION_CORE_EMPTY: prompt too short for shot {shot.get('id')!r} "
            f"(len={len(compact)}); need action/dialogue/camera core"
        )

    # Dialogue must survive into final prompt.
    if dialogue and dialogue not in text:
        raise MotionCoreError(
            f"MOTION_CORE_DIALOGUE_MISSING: spoken_text not in prompt for shot "
            f"{shot.get('id')!r}: {dialogue[:40]!r}"
        )

    # Hero / identity motion needs observable action OR dialogue performance.
    if role_n in {"hero", ""} and mode_n in {
        "i2v",
        "flf",
        "r2v",
        "image_to_video",
        "first_last_frame",
        "reference_to_video",
    }:
        has_visual = bool(actions) or bool(dialogue)
        # Author may put action only in free text — accept body/prop verbs, not camera fillers.
        df = dramatic_function_of(shot)
        low = compact.lower()
        free_ok = any(
            k in low
            for k in (
                "turn",
                "lean",
                "walk",
                "reach",
                "grasp",
                "speak",
                "mouth",
                "hand",
                "hip",
                "body",
                "gaze",
                "kiss",
                "thrust",
                "dramatic function",
                "advances want",
                "visible change",
                "story beat",
                "primary action",
                "opening state",
            )
        )
        # Camera-only filler (push-in / blink / breath) is NOT enough for hero I2V
        camera_only = (
            any(k in low for k in ("push-in", "push in", "dolly", "ken burns", "zoom"))
            and not has_visual
        )
        if camera_only and not free_ok:
            raise MotionCoreError(
                f"MOTION_CORE_CAMERA_ONLY: shot {shot.get('id')!r} has camera filler "
                f"without body/prop action or dialogue — camera serves visible_change, "
                f"does not replace it"
            )
        if not has_visual and not free_ok and not df:
            raise MotionCoreError(
                f"MOTION_CORE_NO_ACTION: shot {shot.get('id')!r} hero motion needs "
                f"dsl.action/motion/visible_change, dialogue, or dramatic_function"
            )

    # Env t2v still needs some scene text.
    if role_n in {"env", "bridge"} and mode_n in {"t2v", "text_to_video"}:
        if len(compact) < 40:
            raise MotionCoreError(
                f"MOTION_CORE_ENV_THIN: env/bridge t2v prompt too thin for {shot.get('id')!r}"
            )

    return {
        "ok": True,
        "shot_id": shot.get("id"),
        "mode": mode_n,
        "role": role_n,
        "prompt_len": len(compact),
        "has_dialogue": bool(dialogue),
        "motion_tier": motion_tier_for(shot),
        "dramatic_function": dramatic_function_of(shot) or None,
    }

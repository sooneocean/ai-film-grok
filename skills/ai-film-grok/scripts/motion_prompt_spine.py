#!/usr/bin/env python3
"""Motion Prompt Spine — film core → motion generation (Grok + H3 shared).

Order (author-facing prompt body):
  dramatic_function → want_beat → action/motion/visible_change
  → camera_prompt → dialogue/foley audio → (provider prefix separate)

Fail-closed rules live in ``assert_motion_prompt_core``.
"""

from __future__ import annotations

from typing import Any


class MotionCoreError(ValueError):
    """Raised when a motion prompt is missing film-core payload."""


_HIGH_HEAT = frozenset({"act", "climax", "peak", "afterglow"})
_HIGH_DF = frozenset({"action", "climax", "hook", "impact", "peak"})
_SOFT_DF = frozenset({"reaction", "afterglow", "bridge", "insert", "sensory"})


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


def motion_tier_for(shot: dict[str, Any]) -> str:
    """soft | medium | high — optical energy expectation for gates/prompts."""
    heat = heat_phase_of(shot)
    df = dramatic_function_of(shot)
    wardrobe = str(shot.get("wardrobe_state") or "").strip().lower()
    if wardrobe in {"bare", "undressed", "nude"} or heat in _HIGH_HEAT:
        if df in _SOFT_DF and heat in {"afterglow"}:
            return "medium"
        return "high"
    if df in _HIGH_DF or heat in {"foreplay", "build"}:
        return "high" if df in {"action", "climax", "hook"} else "medium"
    if df in _SOFT_DF:
        return "soft"
    dialogue = bool(spoken_dialogue_text(shot))
    if dialogue and shot_screen_mode(shot) in {"on_camera", ""}:
        return "medium"
    return "medium"


def dsl_action_parts(shot: dict[str, Any]) -> list[str]:
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    parts: list[str] = []
    for key in ("action", "motion", "visible_change"):
        val = str(dsl.get(key) or "").strip()
        if val and val.lower() not in {"needs_authoring", "tbd", "todo", "n/a"}:
            parts.append(val)
    nar = str(shot.get("nar") or "").strip()
    # Only append short nar as visual fallback when dsl empty (avoid VO dump).
    if not parts and nar and len(nar) <= 120:
        parts.append(nar)
    return parts


def camera_clause(shot: dict[str, Any]) -> str:
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    cam = str(dsl.get("camera_prompt") or "").strip()
    if cam:
        return cam
    framing = str(shot.get("framing") or dsl.get("framing") or "").strip()
    if framing:
        return f"Framing: {framing}"
    return ""


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
    return {
        "dramatic_function": df or None,
        "heat_phase": heat or None,
        "want_beat": want_beat_line(spec, shot) or None,
        "motion_tier": motion_tier_for(shot),
        "spoken_text": dialogue or None,
        "screen_mode": shot_screen_mode(shot) or None,
        "speaker": str(shot.get("speaker") or "").strip() or None,
        "has_action_core": bool(actions) or bool(dialogue),
        "action_summary": ". ".join(actions) if actions else None,
        "camera_prompt": camera_clause(shot) or None,
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
    if not body:
        body = "subtle camera push-in, natural motion, readable physical change."
    if include_provider_prefix:
        return f"{provider_prefix(mode)} {body}".strip()
    return body


def ensure_motion_core_in_prompt(
    text: str,
    spec: dict[str, Any] | None,
    shot: dict[str, Any],
) -> str:
    """Merge missing core clauses into an author prompt (idempotent)."""
    base = (text or "").strip()
    if not base:
        return build_motion_prompt(spec, shot, mode="i2v", include_provider_prefix=False)

    out = base
    df = dramatic_function_of(shot)
    if (
        df
        and f"Dramatic function: {df}" not in out
        and f"dramatic function: {df}" not in out.lower()
    ):
        out = f"Dramatic function: {df}. {out}"

    want = want_beat_line(spec, shot)
    if want and want not in out and "advances want" not in out.lower():
        # Insert after DF if present, else prepend after first sentence-ish
        out = f"{out.rstrip()} {want}"

    tier = motion_tier_for(shot)
    if tier == "high" and "HIGH MOTION" not in out.upper():
        heat = heat_phase_of(shot)
        if heat in _HIGH_HEAT or dramatic_function_of(shot) in _HIGH_DF:
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
    if role_n in {"hero", ""} and mode_n in {"i2v", "r2v", "image_to_video", "reference_to_video"}:
        has_visual = bool(actions) or bool(dialogue)
        # Author may put action only in free text — accept if prompt has motion verbs
        # or explicit dramatic function.
        df = dramatic_function_of(shot)
        free_ok = any(
            k in compact.lower()
            for k in (
                "motion",
                "push",
                "turn",
                "lean",
                "walk",
                "speak",
                "mouth",
                "breath",
                "hand",
                "body",
                "gaze",
                "dramatic function",
                "advances want",
            )
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

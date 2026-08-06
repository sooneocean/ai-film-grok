#!/usr/bin/env python3
"""H3 Timeline Prompt Compiler (Layer 4) — shot → timed motion script for MiniMax H3.

Not a screenplay or storyboard system. Covers only:

  shot / beat → continuous timecode segments → model-ready prompt

Core chain:
  duration → segment count → events → subject action → camera → env motion
  → implied sound → continuous timeline

Format:
  [0s-2s] ...
  [2s-5s] ...
  [5s-8s] ...

Gaps and overlaps are forbidden. Each segment is one dynamic unit
(setting + subject + action + camera + mood + implied sound), with
at most one primary action (+ optional secondary reaction).
"""

from __future__ import annotations

import os
import re
from typing import Any

# Duration → recommended segment count (min, max). ~2–3s per clear action.
_DURATION_SEGMENTS: list[tuple[float, int, int]] = [
    (5.0, 2, 3),
    (8.0, 3, 4),
    (10.0, 4, 5),
    (15.0, 5, 8),
    (30.0, 8, 12),
]

_TIMECODE_RE = re.compile(
    r"\[(\d+(?:\.\d+)?)\s*s\s*-\s*(\d+(?:\.\d+)?)\s*s\]",
    re.IGNORECASE,
)

# Soft env motion templates by tier (raise dynamic density without new plot events).
_ENV_BY_TIER: dict[str, list[str]] = {
    "soft": [
        "soft ambient light shifts across surfaces",
        "fabric and hair micro-drift with quiet air",
        "subtle dust motes drift in the light",
    ],
    "medium": [
        "rain or air moves through the space",
        "reflections flicker on wet surfaces",
        "background elements sway with light parallax",
    ],
    "high": [
        "steam, dust, or rain surges with the action",
        "lights flicker and hard reflections whip across surfaces",
        "environment particles and fabric snap with inertia",
    ],
}


def timeline_prompt_enabled() -> bool:
    """Default ON for H3. Escape: AIFILM_H3_TIMELINE=0."""
    raw = os.environ.get("AIFILM_H3_TIMELINE", "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def has_timeline_markers(text: str) -> bool:
    return bool(_TIMECODE_RE.search(text or ""))


def resolve_duration_sec(
    shot: dict[str, Any] | None,
    *,
    default: float = 5.0,
    max_cap: float = 15.0,
) -> float:
    """Pick generation length from shot / dsl / h3 intent fields."""
    sh = shot if isinstance(shot, dict) else {}
    dsl = sh.get("dsl") if isinstance(sh.get("dsl"), dict) else {}
    candidates = [
        sh.get("duration_sec"),
        sh.get("max_duration_sec"),
        sh.get("duration"),
        dsl.get("duration_sec"),
        dsl.get("max_duration_sec"),
        dsl.get("duration"),
    ]
    for raw in candidates:
        if raw is None or raw == "":
            continue
        try:
            val = float(raw)
        except (TypeError, ValueError):
            continue
        if val > 0:
            return max(2.0, min(float(max_cap), val))
    return max(2.0, min(float(max_cap), float(default)))


def segment_count_for(
    duration_sec: float,
    *,
    prompt_tier: str = "medium",
    n_events: int | None = None,
) -> int:
    """Map duration → segment count; denser for high motion, sparser for soft."""
    dur = max(2.0, float(duration_sec))
    lo, hi = 2, 3
    for limit, a, b in _DURATION_SEGMENTS:
        if dur <= limit + 1e-6:
            lo, hi = a, b
            break
    else:
        lo, hi = 8, 12

    tier = (prompt_tier or "medium").strip().lower()
    if tier == "soft":
        n = lo
    elif tier == "high":
        n = hi
    else:
        n = (lo + hi) // 2

    if n_events is not None and n_events > 0:
        # Cap event density: ~one primary action per segment.
        n = max(lo, min(hi, max(n, min(n_events, hi))))
    # Keep ~1.5–3.5s per segment when possible.
    max_by_time = max(2, int(round(dur / 1.6)))
    min_by_time = max(2, int(round(dur / 3.2)))
    n = max(min_by_time, min(max_by_time, n))
    return max(2, min(12, n))


def plan_segment_bounds(duration_sec: float, n_segments: int) -> list[tuple[float, float]]:
    """Continuous coverage [0, duration] with no gaps or overlaps."""
    dur = max(2.0, float(duration_sec))
    n = max(1, int(n_segments))
    # Prefer integer-ish boundaries for short clips (H3 friendly).
    if dur <= 15 and abs(dur - round(dur)) < 1e-6:
        total = int(round(dur))
        base = total // n
        rem = total - base * n
        bounds: list[tuple[float, float]] = []
        t = 0
        for i in range(n):
            # Put leftover seconds on middle/late segments (action peak).
            extra = 1 if i >= (n - rem) else 0
            end = t + base + extra
            if i == n - 1:
                end = total
            bounds.append((float(t), float(end)))
            t = end
        return bounds

    step = dur / n
    bounds = []
    for i in range(n):
        a = round(i * step, 2)
        b = round(dur if i == n - 1 else (i + 1) * step, 2)
        bounds.append((a, b))
    return bounds


def format_timecode(start: float, end: float) -> str:
    def clean(x: float) -> str:
        if abs(x - round(x)) < 1e-6:
            return f"{int(round(x))}s"
        return f"{x:.1f}s"

    return f"[{clean(start)}-{clean(end)}]"


def camera_cut_mode(shot: dict[str, Any]) -> str:
    """continuous | multi — whether segments are phases of one shot or cuts."""
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    raw = (
        str(dsl.get("camera_cut_mode") or dsl.get("cut_mode") or shot.get("camera_cut_mode") or "")
        .strip()
        .lower()
    )
    if raw in {"multi", "multicut", "cut", "cuts", "edit", "montage"}:
        return "multi"
    if raw in {"continuous", "single", "one_shot", "oners"}:
        return "continuous"
    # Continue chains and default I2V are one continuous take.
    if str(dsl.get("chain_mode") or "").lower() == "continue" or shot.get("parent_shot_id"):
        return "continuous"
    return "continuous"


def _split_event_seeds(shot: dict[str, Any]) -> list[str]:
    """Pull discrete event seeds from dsl + content channels (max density control)."""
    from motion_prompt_spine import dsl_action_parts

    parts = dsl_action_parts(shot)
    seeds: list[str] = []
    for p in parts:
        # Split on "; " or " then " lightly; keep short clauses whole.
        chunks = re.split(r"\s*;\s*|\s+then\s+|\s+,\s+(?=[A-Z])", p)
        for c in chunks:
            c = " ".join(c.split()).strip(" .")
            if c and c.lower() not in {"needs_authoring", "tbd", "todo", "n/a"}:
                seeds.append(c)
    # Author explicit timeline events
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    explicit = dsl.get("timeline_events") or dsl.get("events") or shot.get("timeline_events")
    if isinstance(explicit, list):
        out = []
        for e in explicit:
            if isinstance(e, str) and e.strip():
                out.append(e.strip())
            elif isinstance(e, dict):
                t = str(e.get("action") or e.get("text") or e.get("event") or "").strip()
                if t:
                    out.append(t)
        if out:
            return out
    return seeds


def _camera_seed(shot: dict[str, Any]) -> str:
    from motion_prompt_spine import camera_clause

    cam = camera_clause(shot)
    if cam:
        return cam
    tier_hint = {
        "soft": "locked camera, micro push only if needed",
        "medium": "slow continuous camera move matching the action",
        "high": "energetic handheld or dynamic track following the body",
    }
    try:
        from motion_prompt_spine import motion_tier_for

        return tier_hint.get(motion_tier_for(shot), tier_hint["medium"])
    except Exception:
        return tier_hint["medium"]


def _env_seed(shot: dict[str, Any], index: int, tier: str) -> str:
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    env = str(dsl.get("environment") or dsl.get("env_motion") or shot.get("environment") or "").strip()
    if env:
        return env
    bank = _ENV_BY_TIER.get(tier, _ENV_BY_TIER["medium"])
    return bank[index % len(bank)]


def _primary_secondary(seeds: list[str], index: int, n: int) -> tuple[str, str]:
    """One primary action; optional secondary reaction. No 7-verb dumps."""
    if not seeds:
        # Progressive generic arc when author left only framing.
        arc = [
            "subject holds readable presence and begins a clear physical beat",
            "primary action develops with visible body/pose change",
            "action peaks with decisive movement",
            "motion settles into a stable readable pose",
        ]
        primary = arc[min(index, len(arc) - 1)]
        return primary, ""
    if len(seeds) == 1:
        # Stretch single seed across arc: start → develop → resolve.
        base = seeds[0]
        if n <= 2:
            if index == 0:
                return f"{base} begins", "body prepares"
            return f"{base} completes and holds", ""
        if index == 0:
            return f"{base} begins from a clear start pose", ""
        if index == n - 1:
            return f"{base} resolves into a stable end pose", ""
        return f"{base} continues with progressive intensity", ""
    # Map seeds across segments; avoid packing all into one segment.
    if index < len(seeds):
        primary = seeds[index]
        secondary = seeds[index + 1] if (index + 1 < len(seeds) and index == n - 1) else ""
        # Only last segment may absorb leftover as secondary (one max).
        if index == n - 1 and len(seeds) > n:
            # Prefer last remaining seed as secondary, not a laundry list.
            secondary = seeds[-1] if seeds[-1] != primary else ""
        return primary, secondary
    # More segments than seeds: resolve / hold.
    return f"{seeds[-1]} holds and settles", ""


def continuity_header(
    shot: dict[str, Any],
    *,
    mode: str = "i2v",
    compact: bool | None = None,
) -> str:
    cut = camera_cut_mode(shot)
    # Dialogue CU: short lock — long meta dumps freeze mouth performance on H3.
    if compact is None:
        try:
            from motion_prompt_spine import spoken_dialogue_text

            compact = bool(spoken_dialogue_text(shot))
        except Exception:
            compact = False
    if compact:
        lines = [
            "Continuity: same face, hair, wardrobe, identity locked.",
            "One primary mouth/body action per segment; describe motion not static frames.",
            "Final segment holds a clear end expression after speech.",
        ]
        if cut != "multi":
            lines.append("Single continuous take, locked camera preferred.")
        return " ".join(lines)

    lines = [
        "Continuity anchor: maintain the same character appearance, clothing, hairstyle, "
        "props, face identity, and spatial orientation throughout all segments.",
        "Scene continuity: location, weather, time of day, and lighting direction stay "
        "consistent; each segment continues from the previous ending state.",
        "Each segment contains one primary action and at most one secondary reaction. "
        "Describe motion, not static frames.",
    ]
    if cut == "multi":
        lines.append(
            "Camera mode: multi-cut — clean cut at the start of a segment only when framing "
            "intentionally changes; otherwise hold continuity."
        )
    else:
        lines.append(
            "Camera mode: single continuous take — one continuous camera move across all "
            "segments (phases of the same shot, not hard cuts)."
        )
    lines.append(
        "Final segment must resolve into a clear ending pose, composition, or environmental "
        "beat rather than cutting off mid-action."
    )
    # Mode-specific identity (I2V/R2V already have prefix; reinforce for T2V env).
    m = (mode or "i2v").strip().lower()
    if m in {"t2v", "text_to_video"}:
        lines.append("No new faces or characters unless the text explicitly requires them.")
    # 2V reference anchor: lock to the reference image composition.
    if m in {"i2v", "flf", "r2v"}:
        lines.append(
            "2V reference anchor: the start frame is derived from the reference "
            "image; preserve its composition, subject identity, and spatial "
            "orientation throughout the timeline."
        )
    return " ".join(lines)


# ── 2V Reference Stage ──────────────────────────────────────────


def supports_image_input(mode: str) -> bool:
    """Return True when the H3 mode accepts image reference input (2V)."""
    return mode.strip().lower() in {"i2v", "flf", "r2v"}


def build_reference_composition_prompt(
    shot: dict[str, Any],
    *,
    mode: str = "i2v",
) -> str:
    """Generate a Grok image-model prompt for the ideal first-frame composition.

    Used in the 2V reference stage: Grok generates a high-quality reference
    image from this prompt, which then serves as the start frame for H3 video
    generation.

    The prompt includes scene setting, subject identity, camera direction,
    lighting, mood, shot size, lens, depth of field, color palette, motion
    tier, and mode-specific composition guidance for maximum control.
    """
    from motion_prompt_spine import (
        camera_clause,
        motion_tier_for,
    )

    mode = (mode or "i2v").strip().lower()
    setting = _extract_setting(shot)
    subject = _extract_subject(shot)
    cam = camera_clause(shot) or "medium shot, steady framing"
    mood = _mood_seed(shot)
    lighting = _extract_lighting(shot)
    tier = motion_tier_for(shot)
    shot_size = _extract_shot_size(shot)
    palette = _extract_color_palette(shot)
    dof = _extract_depth_of_field(shot)
    lens = _extract_lens_hint(shot)

    # Tier-based motion guidance
    tier_guidance = {
        "soft": "Soft motion: micro-performance only (eyes, breath, jaw); locked camera preferred.",
        "medium": "Medium motion: visible body/pose change with steady camera.",
        "high": "High motion: large visible pose/body change; dynamic camera track.",
    }.get(tier, "Medium motion: visible body/pose change with steady camera.")

    # Mode-specific composition focus
    mode_focus = {
        "i2v": "Lock the subject identity and wardrobe exactly; the first frame must be the starting pose for motion generation.",
        "flf": "First-last frame composition: the first frame establishes the opening pose; the last frame (if provided) establishes the landing pose. Maintain identity across both.",
        "r2v": "Energy-first composition: emphasize the subject's dynamic pose and facial expression; the reference frame should capture the peak energy moment.",
    }.get(mode, "Lock the subject identity and wardrobe exactly.")

    parts = [
        "Composition reference frame for video generation.",
        setting,
        subject,
        f"Shot: {shot_size}",
        f"Camera: {cam}",
        f"Lens: {lens}",
        f"Depth of field: {dof}",
        f"Lighting: {lighting}",
        f"Color palette: {palette}",
        f"Mood: {mood}",
        f"Motion tier: {tier}",
        tier_guidance,
        mode_focus,
        "9:16 aspect ratio. Cinematic quality. High detail. This image serves as the "
        "start frame for motion generation.",
    ]
    return " ".join(p for p in parts if p)


def inject_2v_reference_stage(
    prompt: str,
    shot: dict[str, Any],
    *,
    ref_image_paths: list[str] | None = None,
    mode: str = "i2v",
) -> str:
    """When 2V + reference images available, prepend the reference stage to the prompt.

    Returns the enhanced prompt with:
      1. Reference image generation instruction (Grok image model)
      2. Existing reference images reused as composition anchors
      3. Timeline segments that anchor to the reference frame
    """
    if not ref_image_paths:
        return prompt

    mode = (mode or "i2v").strip().lower()
    comp_prompt = build_reference_composition_prompt(shot, mode=mode)

    # Build existing reference image section
    ref_section = _build_ref_image_section(ref_image_paths, mode)

    stage_header = (
        "=== 2V REFERENCE STAGE ===\n"
        f"Mode: {mode}\n"
        "Step 1: Generate or refine the reference composition image.\n"
        f"Composition prompt: {comp_prompt}\n"
        f"{ref_section}"
        "Step 2: Use the resulting image as the start frame reference "
        "for video generation.\n"
        "Maintain identity, wardrobe, props, and spatial orientation "
        "from the reference frame throughout all segments.\n"
        "=== TIMELINE ===\n"
    )

    return f"{stage_header}{prompt}"


def _build_ref_image_section(
    ref_image_paths: list[str],
    mode: str,
) -> str:
    """Build a section describing existing reference images to reuse."""
    if not ref_image_paths:
        return ""

    lines = []
    if len(ref_image_paths) == 1:
        lines.append(
            "Reference image available: use it as the primary composition "
            "anchor for the start frame."
        )
    else:
        lines.append(
            f"{len(ref_image_paths)} reference images available: use the "
            "first as the primary composition anchor; use subsequent images "
            "for identity/style consistency."
        )

    # Mode-specific guidance for existing refs
    mode_guidance = {
        "i2v": "The reference image defines the subject's appearance, "
               "wardrobe, and starting pose. Do not alter identity.",
        "flf": "The first reference is the opening frame; the last "
               "reference (if present) defines the landing pose.",
        "r2v": "The reference image defines the energy pose and facial "
               "expression. Prioritize motion over static identity.",
    }
    guidance = mode_guidance.get(mode, "")
    if guidance:
        lines.append(guidance)

    return " ".join(lines)


def _extract_setting(shot: dict[str, Any]) -> str:
    """Extract the scene/setting description from a shot dict."""
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    env = str(
        dsl.get("environment") or dsl.get("env") or shot.get("environment") or ""
    ).strip()
    if env:
        return env
    df = str(shot.get("dramatic_function") or "").strip().lower()
    setting_map = {
        "action": "a dynamic urban environment",
        "climax": "an intense dramatic setting",
        "afterglow": "a quiet, atmospheric space",
        "hook": "a compelling opening scene",
        "approach": "a transitional space",
        "reaction": "an intimate interior",
    }
    return setting_map.get(df, "a cinematic scene")


def _extract_subject(shot: dict[str, Any]) -> str:
    """Extract the subject description from a shot dict."""
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    subject = str(
        dsl.get("subject")
        or dsl.get("character")
        or shot.get("subject")
        or ""
    ).strip()
    if subject:
        return subject
    return "the main character"


def _extract_lighting(shot: dict[str, Any]) -> str:
    """Extract lighting description from a shot dict."""
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    lighting = str(dsl.get("lighting") or shot.get("lighting") or "").strip()
    if lighting:
        return lighting
    return "natural cinematic lighting"


def _extract_shot_size(shot: dict[str, Any]) -> str:
    """Extract shot size from a shot dict for composition guidance."""
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    raw = str(
        dsl.get("shot_size")
        or dsl.get("framing")
        or shot.get("shot_size")
        or shot.get("framing")
        or ""
    ).strip().lower()
    if raw:
        return raw
    df = str(shot.get("dramatic_function") or "").strip().lower()
    size_map = {
        "action": "wide",
        "climax": "medium-wide",
        "afterglow": "close-up",
        "hook": "wide",
        "approach": "medium",
        "reaction": "close-up",
    }
    return size_map.get(df, "medium shot")


def _extract_color_palette(shot: dict[str, Any]) -> str:
    """Extract color palette hints from a shot dict."""
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    palette = str(
        dsl.get("color_palette") or dsl.get("palette") or shot.get("color_palette") or ""
    ).strip()
    if palette:
        return palette
    heat = str(shot.get("heat_phase") or "").strip().lower()
    df = str(shot.get("dramatic_function") or "").strip().lower()
    if heat in {"act", "climax"} or df in {"action", "climax", "impact", "peak"}:
        return "high contrast, saturated warm tones"
    if heat == "afterglow" or df in {"afterglow", "reaction"}:
        return "soft cool tones, desaturated"
    if df in {"hook", "approach"}:
        return "muted tones with a single warm accent"
    return "natural cinematic palette"


def _extract_depth_of_field(shot: dict[str, Any]) -> str:
    """Extract depth of field hint from a shot dict."""
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    dof = str(
        dsl.get("depth_of_field") or dsl.get("dof") or shot.get("depth_of_field") or ""
    ).strip().lower()
    if dof:
        return dof
    shot_size = _extract_shot_size(shot).lower()
    if any(k in shot_size for k in ("close", "cu", "ecu", "extreme")):
        return "shallow (subject sharp, background soft)"
    if any(k in shot_size for k in ("wide", "ws", "ew", "extreme wide")):
        return "deep (everything in focus)"
    return "medium (subject sharp, gentle background falloff)"


def _extract_lens_hint(shot: dict[str, Any]) -> str:
    """Extract lens hint from a shot dict for composition guidance."""
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    lens = str(dsl.get("lens") or dsl.get("focal_length") or shot.get("lens") or "").strip()
    if lens:
        return lens
    shot_size = _extract_shot_size(shot).lower()
    if any(k in shot_size for k in ("close", "cu", "ecu")):
        return "85mm f/1.4"
    if any(k in shot_size for k in ("medium", "ms")):
        return "50mm f/1.8"
    if any(k in shot_size for k in ("wide", "ws")):
        return "35mm f/2.0"
    return "50mm f/1.8"


def _mood_seed(shot: dict[str, Any]) -> str:
    df = str(shot.get("dramatic_function") or "").strip().lower()
    heat = str(shot.get("heat_phase") or "").strip().lower()
    if heat in {"act", "climax"} or df in {"action", "climax", "impact", "peak"}:
        return "high-energy charged atmosphere"
    if heat == "afterglow" or df in {"afterglow", "reaction"}:
        return "soft lingering afterglow mood"
    if df in {"hook", "approach"}:
        return "tension-building atmosphere"
    return "cinematic natural mood"


def _dialogue_in_segment(
    shot: dict[str, Any],
    index: int,
    n: int,
    *,
    dialogue: str,
    screen: str,
) -> str:
    """Place spoken line in a middle-ish segment for lip-sync priority."""
    if not dialogue:
        return ""
    # Prefer segment near 40–60% of clip for on-camera speech.
    target = max(0, min(n - 1, n // 2 if n > 2 else 0))
    if index != target:
        return ""
    if screen == "off_camera":
        return (
            f'off-camera Mandarin line continues: 「{dialogue}」 '
            f"(voice present, mouth may be out of frame)"
        )
    return (
        f'character speaks on camera in natural Mandarin with visible lip sync; '
        f'line: 「{dialogue}」'
    )


def build_segment_lines(
    spec: dict[str, Any] | None,
    shot: dict[str, Any],
    *,
    duration_sec: float | None = None,
    prompt_tier: str | None = None,
    n_segments: int | None = None,
    inject_continuity_in_first: bool = True,
) -> list[str]:
    """Return list of '[0s-2s] ...' lines (no provider prefix)."""
    from motion_prompt_spine import motion_tier_for, shot_screen_mode, spoken_dialogue_text

    dur = (
        resolve_duration_sec(shot, default=duration_sec or 5.0)
        if duration_sec is None
        else float(duration_sec)
    )
    tier = (prompt_tier or motion_tier_for(shot)).strip().lower()
    seeds = _split_event_seeds(shot)
    n = (
        int(n_segments)
        if n_segments is not None
        else segment_count_for(dur, prompt_tier=tier, n_events=len(seeds) or None)
    )
    n = max(2, min(12, n))
    bounds = plan_segment_bounds(dur, n)
    cam = _camera_seed(shot)
    mood = _mood_seed(shot)
    dialogue = spoken_dialogue_text(shot)
    screen = shot_screen_mode(shot)
    cut = camera_cut_mode(shot)
    cont = continuity_header(shot, mode=str(shot.get("h3_mode") or "i2v"))

    lines: list[str] = []
    for i, (a, b) in enumerate(bounds):
        primary, secondary = _primary_secondary(seeds, i, n)
        env = _env_seed(shot, i, tier)
        dlg = _dialogue_in_segment(shot, i, n, dialogue=dialogue, screen=screen)

        # Segment formula: Setting/Subject + Action + Camera + Mood + Env (+ speech)
        bits: list[str] = []
        if i == 0:
            if inject_continuity_in_first:
                bits.append(cont)
            bits.append("Opening state readable from the start frame")
        bits.append(f"Primary action: {primary}")
        if secondary:
            bits.append(f"Secondary reaction: {secondary}")
        if cut == "multi" and i > 0:
            bits.append(f"Clean cut into: {cam}")
        else:
            bits.append(f"Camera: {cam}")
        bits.append(f"Environment in motion: {env}")
        bits.append(f"Mood: {mood}")
        if dlg:
            bits.append(dlg)
        # Implied sound via visible event (no separate audio prompt block here)
        bits.append("Implied diegetic sound follows visible physical events")
        if i == n - 1:
            bits.append("Resolves into a clear ending pose and composition")

        body = "; ".join(bits) + "."
        lines.append(f"{format_timecode(a, b)} {body}")
    return lines


def compile_timeline_body(
    spec: dict[str, Any] | None,
    shot: dict[str, Any],
    *,
    duration_sec: float | None = None,
    include_film_core: bool = True,
    include_audio_clause: bool = True,
) -> str:
    """Semantic body: optional DF/want + continuity + timeline (+ audio clause)."""
    from motion_prompt_spine import (
        audio_clause,
        dramatic_function_of,
        motion_tier_for,
        want_beat_line,
    )

    chunks: list[str] = []
    if include_film_core:
        df = dramatic_function_of(shot)
        if df:
            chunks.append(f"Dramatic function: {df}.")
        want = want_beat_line(spec, shot)
        if want:
            chunks.append(want if want.endswith(".") else f"{want}.")
        tier = motion_tier_for(shot)
        if tier == "high":
            chunks.append(
                "HIGH MOTION priority: large visible pose/body change across the timeline; "
                "avoid frozen portrait or micro-breath-only."
            )
        elif tier == "soft":
            chunks.append(
                "SOFT MOTION: micro-performance only (eyes, breath, jaw); locked camera preferred."
            )

    chunks.append(continuity_header(shot, mode=str(shot.get("h3_mode") or "i2v")))
    chunks.extend(build_segment_lines(spec, shot, duration_sec=duration_sec))

    if include_audio_clause:
        # Keep film-core audio inject (dialogue line / ambience) for fail-closed asserts.
        chunks.append(audio_clause(shot))

    return " ".join(c for c in chunks if c and str(c).strip()).strip()


def compile_h3_timeline_prompt(
    spec: dict[str, Any] | None,
    shot: dict[str, Any],
    *,
    mode: str = "i2v",
    duration_sec: float | None = None,
    include_provider_prefix: bool = True,
) -> str:
    """Full H3-ready prompt: geometry prefix + timed motion script."""
    from motion_prompt_spine import provider_prefix

    shot_x = dict(shot) if isinstance(shot, dict) else {}
    shot_x["h3_mode"] = mode
    body = compile_timeline_body(
        spec,
        shot_x,
        duration_sec=duration_sec,
        include_film_core=True,
        include_audio_clause=True,
    )
    try:
        from input_fidelity import inject_story_beat_into_prompt

        body = inject_story_beat_into_prompt(body, shot_x)
    except Exception:
        pass
    if include_provider_prefix:
        return f"{provider_prefix(mode)} {body}".strip()
    return body


def merge_timeline_into_author(
    author: str,
    spec: dict[str, Any] | None,
    shot: dict[str, Any],
    *,
    duration_sec: float | None = None,
) -> str:
    """If author prompt has no timecodes, append continuity + timeline segments."""
    base = (author or "").strip()
    if not base:
        return compile_timeline_body(spec, shot, duration_sec=duration_sec)
    if has_timeline_markers(base):
        return base
    cont = continuity_header(shot)
    segs = " ".join(build_segment_lines(spec, shot, duration_sec=duration_sec))
    return f"{base.rstrip()} {cont} {segs}".strip()


def validate_timeline_coverage(
    text: str,
    *,
    duration_sec: float | None = None,
    tol: float = 0.05,
) -> dict[str, Any]:
    """Machine check: starts at 0, continuous, optional end match, no overlap."""
    matches = list(_TIMECODE_RE.finditer(text or ""))
    if not matches:
        return {
            "ok": False,
            "error": "NO_TIMECODES",
            "segments": [],
        }
    segs: list[dict[str, float]] = []
    for m in matches:
        a, b = float(m.group(1)), float(m.group(2))
        segs.append({"start": a, "end": b})
    issues: list[str] = []
    if segs[0]["start"] > tol:
        issues.append(f"FIRST_NOT_ZERO:{segs[0]['start']}")
    for i in range(len(segs) - 1):
        if segs[i]["end"] > segs[i + 1]["start"] + tol:
            issues.append(f"OVERLAP@{i}")
        elif segs[i + 1]["start"] - segs[i]["end"] > tol:
            issues.append(f"GAP@{i}:{segs[i]['end']}→{segs[i + 1]['start']}")
        if segs[i]["end"] <= segs[i]["start"]:
            issues.append(f"NON_POSITIVE@{i}")
    if segs[-1]["end"] <= segs[-1]["start"]:
        issues.append("NON_POSITIVE@last")
    if duration_sec is not None and abs(segs[-1]["end"] - float(duration_sec)) > max(tol, 0.51):
        issues.append(f"END_MISMATCH:{segs[-1]['end']}!={duration_sec}")
    return {
        "ok": not issues,
        "error": issues[0] if issues else None,
        "issues": issues,
        "segments": segs,
        "segment_count": len(segs),
        "coverage_end": segs[-1]["end"] if segs else 0.0,
    }

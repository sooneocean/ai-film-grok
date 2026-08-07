"""Official MiniMax H3 prompt dialect compiler (h3-prompt-writing).

Serializes film-spec shots into the MiniMax VIDEO_PROMPT_WRITING_GUIDE formats:

* **Base** (T2VA / I2VA / FL2VA / L2VA): alignment line + three core fields
* **Ref2VA**: six sections (subject_definitions … non_diegetic_music)

Default dialect **auto** (O3 canary 2026-08-07):
  dialogue → official; high-motion → legacy; else official.
Force: ``AIFILM_H3_PROMPT_DIALECT=official|legacy|auto``

Upstream pin: ``references/vendor/minimax-h3/h3-prompt-writing/``
"""

from __future__ import annotations

import os
import re
from typing import Any

_OFF = frozenset({"official", "h3_official", "minimax", "native", "v2"})
_LEG = frozenset(
    {
        "legacy",
        "timeline",
        "temporal",
        "flat",
        "spine",
        "v1",
        "old",
        "h3_timeline",
    }
)
_LEGACY_TC_RE = re.compile(
    r"\[\d+(?:\.\d+)?s\s*-\s*\d+(?:\.\d+)?s\]",
    re.IGNORECASE,
)
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def resolve_prompt_dialect(
    shot: dict[str, Any] | None = None,
    *,
    explicit: str | None = None,
) -> str:
    """Return ``official`` or ``legacy`` (auto policy applied when needed)."""
    if explicit is not None and str(explicit).strip():
        raw = str(explicit).strip().lower()
    else:
        sh = shot if isinstance(shot, dict) else {}
        dsl = sh.get("dsl") if isinstance(sh.get("dsl"), dict) else {}
        raw = str(
            dsl.get("prompt_dialect")
            or dsl.get("prompt_format")
            or sh.get("prompt_dialect")
            or sh.get("prompt_format")
            or os.environ.get("AIFILM_H3_PROMPT_DIALECT")
            or "auto"
        ).strip().lower()
    if raw in _OFF:
        return "official"
    if raw in _LEG:
        return "legacy"
    return _auto_dialect_for_shot(shot if isinstance(shot, dict) else {})


def _auto_dialect_for_shot(shot: dict[str, Any]) -> str:
    try:
        from motion_prompt_spine import motion_tier_for, spoken_dialogue_text

        has_dlg = bool(spoken_dialogue_text(shot))
        tier = motion_tier_for(shot)
    except Exception:
        has_dlg = False
        tier = "medium"
        for cue in shot.get("audio_cues") or []:
            if isinstance(cue, dict) and str(cue.get("spoken_text") or "").strip():
                has_dlg = True
                break
        dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
        tier = str(
            dsl.get("prompt_tier") or shot.get("prompt_tier") or "medium"
        ).lower()
    if has_dlg:
        return "official"
    if tier == "high":
        return "legacy"
    return "official"


def map_official_mode(mode: str) -> str:
    m = (mode or "i2v").strip().lower()
    if m in {"t2v", "text_to_video", "text-to-video"}:
        return "T2VA"
    if m in {"r2v", "ref2v", "reference", "reference_to_video", "ref2va"}:
        return "Ref2VA"
    if m in {"flf", "first_last", "first_last_frame", "i2v_flf", "fl2va"}:
        return "FL2VA"
    if m in {"l2v", "l2va", "last_frame", "last_only"}:
        return "L2VA"
    return "I2VA"


def _dur(shot: dict[str, Any], default: float = 5.0) -> float:
    try:
        return max(2.0, min(8.0, float(shot.get("duration_sec") or default)))
    except Exception:
        return default


def _tier(shot: dict[str, Any]) -> str:
    try:
        from motion_prompt_spine import motion_tier_for

        return str(motion_tier_for(shot) or "medium").lower()
    except Exception:
        dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
        return str(
            dsl.get("prompt_tier") or shot.get("prompt_tier") or "medium"
        ).lower()


def _lang_tag(text: str) -> str:
    """Language label inside <d>[…]. CJK → Mandarin (O3 canary + production)."""
    return "Mandarin" if _CJK_RE.search(text or "") else "English"


def _collect_dialogue_events(shot: dict[str, Any]) -> list[dict[str, str]]:
    """Ordered vocal events for stable (S1), (S2) numbering."""
    events: list[dict[str, str]] = []
    cues = shot.get("audio_cues") if isinstance(shot.get("audio_cues"), list) else []
    for cue in cues:
        if not isinstance(cue, dict):
            continue
        d = str(cue.get("spoken_text") or cue.get("text") or "").strip()
        if not d:
            continue
        sc = str(cue.get("screen_mode") or shot.get("screen_mode") or "on_camera").strip().lower()
        speaker = str(cue.get("speaker") or shot.get("speaker") or "").strip()
        events.append({"text": d, "screen_mode": sc, "speaker": speaker})
    if events:
        return events
    try:
        from motion_prompt_spine import shot_screen_mode, spoken_dialogue_text

        d = spoken_dialogue_text(shot)
        if d:
            return [
                {
                    "text": d,
                    "screen_mode": shot_screen_mode(shot) or "on_camera",
                    "speaker": str(shot.get("speaker") or "").strip(),
                }
            ]
    except Exception:
        pass
    return []


def _format_dialogue_clause(events: list[dict[str, str]], *, subject_label: str = "") -> str:
    if not events:
        return ""
    parts: list[str] = []
    for i, ev in enumerate(events, start=1):
        sid = f"S{i}"
        d = ev["text"]
        lang = _lang_tag(d)
        tag = f"<d>[{lang}] {d}</d>"
        who = subject_label.strip() or "the visible character with a clear natural voice"
        if ev.get("speaker"):
            who = f"{ev['speaker']} with a clear natural voice"
        if ev.get("screen_mode") == "off_camera":
            parts.append(
                f"{who} ({sid}) says in an off-screen voiceover: {tag} "
                "while the on-screen lips remain completely closed"
            )
        else:
            parts.append(
                f"{who} ({sid}) says: {tag} with clear jaw open-close and "
                "visible lip shapes on each syllable"
            )
    return " ".join(parts)


def _dlg(shot: dict[str, Any], *, subject_label: str = "") -> str:
    return _format_dialogue_clause(
        _collect_dialogue_events(shot),
        subject_label=subject_label,
    )


def _action(shot: dict[str, Any]) -> str:
    try:
        from motion_prompt_spine import dsl_action_parts

        parts = dsl_action_parts(shot)
    except Exception:
        dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
        parts = [
            str(dsl.get(k) or "").strip()
            for k in ("action", "motion", "visible_change")
            if str(dsl.get(k) or "").strip()
        ]
    tier = _tier(shot)
    base = "; ".join(parts) if parts else ""
    if tier == "high":
        densify = (
            "large visible pose and body torque every half-second; weight shifts, "
            "hands re-grip, fabric and hair snap with inertia; silhouette changes "
            "continuously — never a frozen portrait"
        )
        return f"{base}; {densify}" if base else densify
    if tier == "soft":
        micro = (
            "continuous micro-life every half-second: soft blinks, breath lifts the chest, "
            "tiny head sway and hair drift; never freeze into a still photo"
        )
        return f"{base}; {micro}" if base else micro
    if base:
        return base
    if _collect_dialogue_events(shot):
        return (
            "the subject begins from the start-frame pose, articulates speech with "
            "natural head micro-motion, and settles into a clear end expression"
        )
    return "continuous natural body motion from the start frame to a clear end pose"


def _cam(shot: dict[str, Any]) -> str:
    """Official camera sentence: motion type + optional amplitude + speed."""
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    raw = " ".join(
        str(x)
        for x in (
            dsl.get("camera_prompt"),
            dsl.get("camera"),
            shot.get("camera_prompt"),
            shot.get("camera"),
        )
        if x
    )
    low = raw.lower()
    tier = _tier(shot)

    # Explicit static / lock
    if re.search(r"\b(lock|static|locked|hold|fixed)\b", low) or (
        tier == "soft" and not re.search(r"push|pan|truck|tilt|zoom|arc|track|pedestal|roll", low)
    ):
        return "The camera holds a static shot"

    amp = ""
    if re.search(r"\b(large|wide|aggressive|whip)\b", low) or tier == "high":
        amp = " with large amplitude"
    elif re.search(r"\b(small|subtle|gentle|slight)\b", low) or tier == "soft":
        amp = " with small amplitude"

    spd = ""
    if re.search(r"\b(fast|quick|rapid|snap|whip)\b", low) or tier == "high":
        spd = " at fast speed"
    elif re.search(r"\b(slow|gentle|gradual)\b", low) or tier == "soft":
        spd = " at slow speed"
    elif amp:
        # medium amplitude/speed usually omitted; keep speed only when useful
        if "large" in amp:
            spd = " at fast speed"
        elif "small" in amp:
            spd = " at slow speed"

    # Motion type priority
    if re.search(r"\b(handheld|shake|jitter)\b", low) or (
        tier == "high" and re.search(r"\b(aggressive|energy)\b", low)
    ):
        strength = "strongly" if tier == "high" or "strong" in low else "slightly"
        return f"The camera shakes {strength}{amp}{spd}".strip()
    if re.search(r"\bzoom\s*out\b", low):
        return f"The camera zooms out{amp}{spd}".strip()
    if re.search(r"\bzoom(\s*in)?\b", low):
        return f"The camera zooms in{amp}{spd}".strip()
    if re.search(r"\bpull\s*out\b|\bdolly\s*out\b", low):
        return f"The camera pulls out{amp}{spd}".strip()
    if re.search(r"\bpush(\s*in)?\b|\bdolly\s*in\b", low):
        return f"The camera pushes in{amp}{spd}".strip()
    if re.search(r"\bpan\s*left\b", low):
        return f"The camera pans left{amp}{spd}".strip()
    if re.search(r"\bpan\s*right\b", low):
        return f"The camera pans right{amp}{spd}".strip()
    if re.search(r"\btruck\s*left\b", low):
        return f"The camera trucks left{amp}{spd}".strip()
    if re.search(r"\btruck\s*right\b", low):
        return f"The camera trucks right{amp}{spd}".strip()
    if re.search(r"\btilt\s*up\b", low):
        return f"The camera tilts up{amp}{spd}".strip()
    if re.search(r"\btilt\s*down\b", low):
        return f"The camera tilts down{amp}{spd}".strip()
    if re.search(r"\bpedestal\s*up\b", low):
        return f"The camera pedestals up{amp}{spd}".strip()
    if re.search(r"\bpedestal\s*down\b", low):
        return f"The camera pedestals down{amp}{spd}".strip()
    if re.search(r"\barc\b", low):
        return f"The camera moves in an arc shot{amp}{spd}".strip()
    if re.search(r"\btrack(ing)?\b|\bfollow\b", low):
        return f"The camera holds a tracking shot{amp}{spd}".strip()
    if re.search(r"\bpov\b", low):
        return "The camera holds a POV"
    if re.search(r"\broll\s*counter", low):
        return f"The camera rolls counterclockwise{amp}{spd}".strip()
    if re.search(r"\broll\b", low):
        return f"The camera rolls clockwise{amp}{spd}".strip()

    if tier == "high":
        return "The camera shakes strongly with large amplitude at fast speed"
    if tier == "soft":
        return "The camera holds a static shot"
    return "The camera pushes in with small amplitude at slow speed"


def _style(shot: dict[str, Any], spec: dict[str, Any] | None = None) -> str:
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    blob = " ".join(
        str(x)
        for x in (
            dsl.get("style"),
            shot.get("style"),
            (spec or {}).get("genre"),
            (spec or {}).get("style"),
        )
        if x
    ).lower()
    if any(k in blob for k in ("live", "photoreal", "live-action", "cinematic real")):
        return "Live-action, cinematic"
    if any(k in blob for k in ("3d", "cg", "cgi")):
        return "3D CG, cinematic"
    if any(k in blob for k in ("watercol",)):
        return "watercolor"
    if any(k in blob for k in ("clay",)):
        return "claymation"
    if any(k in blob for k in ("cel", "anime", "manhua", "manga", "2d")):
        return "2D-animated, medium cel-anime"
    return "Cinematic, 2D-animated"


def _shot_size_phrase(shot: dict[str, Any]) -> str:
    size_tok = str(
        shot.get("shot_size")
        or (shot.get("dsl") or {}).get("shot_size")
        or shot.get("framing")
        or ""
    ).lower().replace(" ", "_")
    if size_tok in {"ecu", "extreme_close", "extreme_closeup", "extreme_close_up"}:
        return "an extreme close-up"
    if size_tok in {"cu", "close", "closeup", "close_up", "mcu"}:
        return "a close-up"
    if size_tok in {"ws", "wide", "wide_shot", "establishing"}:
        return "a wide shot"
    if size_tok in {"ms", "medium", "medium_shot"}:
        return "a medium shot"
    if size_tok in {"mws", "medium_wide"}:
        return "a medium-wide shot"
    return "a medium shot"


def _soundscape(shot: dict[str, Any], *, has_dlg: bool) -> str:
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    custom = str(dsl.get("soundscape") or dsl.get("ambience") or "").strip()
    if custom:
        return custom
    tier = _tier(shot)
    if has_dlg:
        return (
            "Natural room tone and soft fabric movement continue under the spoken line, "
            "with subtle body-shift foley matched to visible motion."
        )
    if tier == "high":
        return (
            "Energetic diegetic ambience and hard fabric/body impact sounds follow the "
            "visible action; cloth snaps, weight thuds, and hair whip stay continuous."
        )
    if tier == "soft":
        return "Soft ambient room tone and gentle air movement; micro fabric rustle only."
    return (
        "Natural diegetic ambience and soft foley matched to the visible action "
        "continue throughout the clip."
    )


def _music(shot: dict[str, Any], spec: dict[str, Any] | None = None) -> str:
    """non_diegetic_music: instrumentation/tempo/dynamics — no abstract mood words."""
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    custom = str(
        dsl.get("non_diegetic_music")
        or dsl.get("score")
        or dsl.get("bgm_prompt")
        or shot.get("non_diegetic_music")
        or ""
    ).strip()
    if custom:
        if custom.upper() in {"N/A", "NA", "NONE", "SILENT", "SILENCE"}:
            return "N/A"
        return custom
    # Film-level audio intent (optional)
    audio = (spec or {}).get("audio") if isinstance(spec, dict) else None
    if isinstance(audio, dict):
        style = str(audio.get("bgm_style") or audio.get("music_style") or "").strip().lower()
        if style in {"rnb", "r&b", "r_n_b"}:
            return (
                "Warm electric-piano chords at a moderate tempo with soft sidechain "
                "bass pulses and sparse brushed drums, gradual low-pass fade at the end."
            )
        if style in {"dark", "horror", "tension"}:
            return (
                "Low sustained strings at a slow tempo with sparse dissonant piano hits "
                "and a quiet high-frequency shimmer that slowly increases then cuts."
            )
        if style and style not in {"none", "off", "n/a", "silent"}:
            return (
                f"Sparse instrumental texture in a {style} register at a moderate tempo, "
                "with restrained dynamics and a short fade-out."
            )
    # Default: H3 native clips usually leave score for post — N/A unless requested
    return "N/A"


def _identity_lock_clause(shot: dict[str, Any], *, has_picture: bool) -> str:
    wardrobe = str(
        shot.get("wardrobe_state")
        or (shot.get("dsl") or {}).get("wardrobe_state")
        or ""
    ).strip().lower()
    bits = []
    if has_picture:
        bits.append(
            "preserving appearance, clothing, hair, and face identity from the reference"
        )
    else:
        bits.append("keeping identity, hair, and wardrobe consistent across the shot")
    if wardrobe in {"bare", "undressed", "nude", "partial"}:
        bits.append("keep first-frame clothing state; never re-dress after undress")
    return "; ".join(bits)


def _format_cut_time(seconds: float) -> str:
    """Official cut marker: MM:SS.mmm within the clip."""
    s = max(0.0, float(seconds))
    mm = int(s // 60)
    ss = s - mm * 60
    return f"{mm:02d}:{ss:06.3f}"


def _segment_action_phrases(shot: dict[str, Any], *, duration_sec: float) -> list[tuple[float, str]]:
    """Optional multi-beat phrases from timeline IR without legacy [0s-2s] markers."""
    try:
        from h3_timeline_prompt import build_segment_lines, segment_count_for

        n = segment_count_for(duration_sec, prompt_tier=_tier(shot))
        # Only multi-shot when we truly have several distinct beats and duration allows
        if n < 3 or duration_sec < 6.0:
            return []
        lines = build_segment_lines(
            None,
            shot,
            duration_sec=duration_sec,
            prompt_tier=_tier(shot),
            n_segments=min(3, n),
            inject_continuity_in_first=False,
        )
        out: list[tuple[float, str]] = []
        for line in lines[1:]:  # skip first; becomes [Shot 1] body
            # strip legacy [0s-2s] if present
            body = _LEGACY_TC_RE.sub("", line).strip()
            # try extract start time from original marker
            m = re.match(
                r"\[(\d+(?:\.\d+)?)\s*s\s*-\s*(\d+(?:\.\d+)?)\s*s\]\s*(.*)",
                line,
                re.I,
            )
            if m:
                t0 = float(m.group(1))
                body = m.group(3).strip()
            else:
                t0 = duration_sec * (len(out) + 1) / max(2, len(lines))
            if body:
                out.append((t0, body))
        return out[:2]  # at most Shot 2 + Shot 3 for short H3 clips
    except Exception:
        return []


def _alignment_line(official: str, *, duration_sec: float, last_shot_n: int = 1) -> str | None:
    if official == "I2VA":
        return (
            "For the target video, at 0.00 seconds into the target video, "
            "<Picture 1> (from [Shot 1]) is fully referenced."
        )
    if official == "FL2VA":
        return (
            "How the reference pictures align with the target video — "
            "Picture 1 (from Shot 1) aligns with the 0.00-second mark of the target video; "
            f"Picture 2 (from Shot {last_shot_n}) aligns with the "
            f"{duration_sec:.2f}-second mark of the target video."
        )
    if official == "L2VA":
        return (
            "How the reference pictures align with the target video — "
            f"<Picture 1> (from [Shot {last_shot_n}]) aligns with the "
            f"{duration_sec:.2f}-second mark of the target video."
        )
    return None


def _build_base_imd(
    shot: dict[str, Any],
    *,
    official: str,
    style: str,
    size: str,
    subject: str,
    action: str,
    cam: str,
    dlg: str,
    tier: str,
    duration_sec: float,
) -> str:
    has_picture = official in {"I2VA", "FL2VA", "L2VA"}
    lock = _identity_lock_clause(shot, has_picture=has_picture)

    if official == "T2VA":
        # No Picture anchors — pure text timeline
        open_body = (
            f"[Shot 1] {style}, {size} frames {subject}. "
            f"{cam} as {action}, {lock}. "
        )
    elif official == "I2VA":
        open_body = (
            f"[Shot 1] {style}, {size} frames {subject} shown in <Picture 1>, {lock}. "
            "The sequence develops forward from the first-frame anchors in <Picture 1>. "
            f"{cam} as {action}. "
        )
    elif official == "FL2VA":
        open_body = (
            f"[Shot 1] {style}, {size} begins from Picture 1 with {subject}, {lock}. "
            "Motion interpolates continuously from Picture 1 toward Picture 2: "
            f"{cam} as {action}. "
            "Intermediate pose, prop, and composition changes remain observable as the "
            "differences progressively narrow toward the last-frame state. "
        )
    elif official == "L2VA":
        open_body = (
            f"[Shot 1] {style}, {size} begins from a plausible preceding state of {subject}, "
            f"compatible with the final landing in <Picture 1>, {lock}. "
            f"{cam} as {action}. "
            "Actions, object states, and composition gradually converge so the final "
            "moments land on the exact arrangement, camera angle, lighting, and pose "
            "established by <Picture 1>. "
        )
    else:
        open_body = f"[Shot 1] {style}, {size} frames {subject}. {cam} as {action}. "

    if tier == "high":
        open_body += "HIGH-ENERGY continuous action path: body silhouette keeps changing. "

    if dlg:
        open_body += dlg + ". "
    else:
        open_body += "No on-screen speech; diegetic physical sounds follow the visible events. "

    # Optional extra official shots from multi-beat IR (rare for ~5s)
    extras = _segment_action_phrases(shot, duration_sec=duration_sec)
    for idx, (t0, body) in enumerate(extras, start=2):
        t_mark = _format_cut_time(t0)
        open_body += (
            f"[Shot {idx}] At {t_mark}, the camera cuts to a continued view of the same "
            f"scene as {body.rstrip('.')}. "
        )

    open_body += (
        "The final moments resolve into a clear ending pose and composition "
        "without freezing mid-action."
    )
    if official == "FL2VA":
        open_body += (
            " By the end of the shot the subject settles into the pose, spacing, and "
            "composition established by Picture 2."
        )
    return open_body



_REF_DUTY = {
    "identity": "identity lock (same face, hair, body)",
    "style": "style and medium lock",
    "pose": "end pose / composition land target (last frame)",
    "wardrobe_state": "wardrobe and body state",
    "contact": "contact / detail insert",
    "last": "end pose land target (last frame)",
    "last_as_pose_ref": "end pose land target (last frame)",
    "end": "end pose land target (last frame)",
    "first": "start frame identity (first frame)",
    "face": "face identity lock",
    "cast": "cast identity lock",
    "reference": "subject reference",
}


def _ref_role(ref: dict[str, Any]) -> str:
    return str(ref.get("role") or ref.get("source") or "reference").strip().lower()


def _ref_duty(role: str) -> str:
    return _REF_DUTY.get(role, "subject reference")


def _merge_official_refs(
    shot: dict[str, Any],
    refs: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Deep-merge explicit refs + shot.media_pack + dsl/h3 ref hints (P2)."""
    out: list[dict[str, Any]] = []
    seen_paths: set[str] = set()

    def _add(item: dict[str, Any]) -> None:
        if not isinstance(item, dict):
            return
        p = str(item.get("path") or item.get("url") or "").strip()
        key = p or f"{_ref_role(item)}:{item.get('label') or item.get('id') or len(out)}"
        if key in seen_paths:
            return
        seen_paths.add(key)
        out.append(dict(item))

    for r in refs or []:
        if isinstance(r, dict):
            _add(r)
        elif r:
            _add({"path": str(r), "role": "reference"})

    pack = shot.get("media_pack") if isinstance(shot.get("media_pack"), dict) else {}
    for r in pack.get("refs") or []:
        if isinstance(r, dict):
            _add(r)
    last = pack.get("last") if isinstance(pack.get("last"), dict) else None
    if last and last.get("path"):
        _add({**last, "role": last.get("role") or "pose", "source": last.get("source") or "media_pack_last"})
    first = pack.get("first") if isinstance(pack.get("first"), dict) else None
    if first and first.get("path"):
        # first is Picture 1 anchor — keep as first role if not already present
        _add({**first, "role": first.get("role") or "first", "source": first.get("source") or "media_pack_first"})

    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    for key in ("h3_refs", "r2v_refs", "reference_images"):
        blob = shot.get(key) or dsl.get(key)
        if isinstance(blob, list):
            for r in blob:
                if isinstance(r, dict):
                    _add(r)
                elif r:
                    _add({"path": str(r), "role": "reference"})
    # path-only last/end stills on shot
    for key, role in (
        ("last_frame", "pose"),
        ("end_still", "pose"),
        ("last_path", "pose"),
        ("pose_ref", "pose"),
    ):
        raw = shot.get(key) or dsl.get(key)
        if raw:
            _add({"path": str(raw), "role": role, "source": key})
    return out


def _env_light_bits(shot: dict[str, Any]) -> str:
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    bits: list[str] = []
    for k in ("location", "setting", "environment", "scene", "place"):
        v = str(dsl.get(k) or shot.get(k) or "").strip()
        if v:
            bits.append(v)
            break
    for k in ("lighting", "light", "time_of_day"):
        v = str(dsl.get(k) or shot.get(k) or "").strip()
        if v:
            bits.append(f"lighting: {v}")
            break
    if not bits:
        bits.append("the same continuous environment as the opening reference")
    return "; ".join(bits)


def _densify_ref_detailed(
    shot: dict[str, Any],
    *,
    style: str,
    size: str,
    subject: str,
    action: str,
    cam: str,
    dlg: str,
    duration_sec: float,
    has_picture2: bool,
) -> str:
    """Aim for GUIDE-like dense detailed_description (soft target ~120–350 words)."""
    tier = _tier(shot)
    env = _env_light_bits(shot)
    wardrobe = str(
        shot.get("wardrobe_state")
        or (shot.get("dsl") or {}).get("wardrobe_state")
        or ""
    ).strip()
    wardrobe_bit = (
        f" Wardrobe state stays {wardrobe} with no re-dress after undress."
        if wardrobe
        else " Wardrobe, hair, and accessories stay locked to the reference."
    )
    beats = [
        (
            f"The target video uses a {style} look with consistent color grading and "
            f"stable key light across the full {duration_sec:.1f}s. "
        ),
        (
            f"[Shot 1] {size} opens on <Subject 1> ({subject}) from <Picture 1> inside "
            f"{env}. {cam} as {action}. "
        ),
        (
            "Composition stays explicit about subject scale in frame, eye-line, "
            "hand/limb positions, and background depth; every half-second shows a "
            "readable body or fabric change rather than a frozen portrait. "
        ),
    ]
    if tier == "high":
        beats.append(
            "HIGH-ENERGY path: weight shifts, torso torque, grip changes, hair and cloth "
            "inertia, and silhouette evolution remain continuous without idle holds. "
        )
    elif tier == "soft":
        beats.append(
            "SOFT path: micro blinks, breath lifts the chest, tiny head sway and hair "
            "drift keep life in the frame without large pose jumps. "
        )
    else:
        beats.append(
            "MEDIUM path: natural weight transfer and small head/hand adjustments "
            "punctuate the action so motion never stalls mid-clip. "
        )
    if dlg:
        if "(S1)" in dlg and not dlg.strip().startswith("<Subject"):
            dlg_body = re.sub(r"^.*? \(S1\)", "<Subject 1> (S1)", dlg, count=1)
            beats.append(f"{dlg_body}. ")
        elif "(S1)" in dlg:
            beats.append(f"{dlg}. ")
        else:
            beats.append(f"<Subject 1> (S1) {dlg}. ")
    else:
        beats.append(
            "No on-screen speech; diegetic physical sounds and fabric foley follow "
            "the visible events only. "
        )
    beats.append(wardrobe_bit + " ")
    if has_picture2:
        beats.append(
            "Motion continuously approaches the landing pose, spacing, and composition "
            "established by <Picture 2>, with intermediate poses remaining observable. "
        )
    beats.append(
        "The final moments resolve into a clear ending pose and composition without "
        "freezing mid-action; identity, hair, and face geometry stay fully preserved."
    )
    return "".join(beats).strip()


def _build_ref2va(
    shot: dict[str, Any],
    *,
    style: str,
    size: str,
    subject: str,
    action: str,
    cam: str,
    dlg: str,
    duration_sec: float,
    refs: list[dict[str, Any]] | None = None,
) -> str:
    """Six-section full-reference rewrite (P2: multi-ref duties + dense detailed)."""
    ref_list = _merge_official_refs(shot, refs)

    definitions: list[str] = [
        f"<Subject 1> is {subject} in <Picture 1>, with locked face identity, hair, and wardrobe."
    ]
    retention: list[str] = [
        "<Subject 1> (appears in [Shot 1]): fully_preserved - identity, hair, and wardrobe retained.",
        "<Picture 1> ([Shot 1] first frame / primary reference): fully_preserved - opening appearance and composition anchor.",
    ]

    # Picture labels: start at 1 for primary still; extra refs map to Picture 2+
    # Prefer pose/last as Picture 2; identity/style as Subject 2 or next Picture.
    picture_n = 1
    subject_n = 1
    saw_pose_picture = False
    for ref in ref_list:
        role = _ref_role(ref)
        duty = _ref_duty(role)
        if role in {"first"}:
            # already covered by Picture 1; annotate duty only once
            if not any("start frame" in d for d in definitions):
                definitions.append(
                    f"<Picture 1> duty: {duty}."
                )
            continue
        if role in {"pose", "last", "end", "last_as_pose_ref"}:
            if not saw_pose_picture:
                picture_n = max(picture_n, 2)
                saw_pose_picture = True
                definitions.append(
                    f"<Picture 2> is the end-pose / landing reference for [Shot 1], "
                    f"defining the final body pose and composition target ({duty})."
                )
                retention.append(
                    "<Picture 2> ([Shot 1] end pose): fully_preserved - final landing pose and framing target."
                )
            continue
        if role in {"identity", "cast", "style", "face"}:
            subject_n = max(subject_n, 2)
            if not any(f"<Subject {subject_n}>" in d for d in definitions):
                definitions.append(
                    f"<Subject {subject_n}> is an identity/style reference ({role}) "
                    f"supporting <Subject 1> — {duty}."
                )
                retention.append(
                    f"<Subject {subject_n}> (appears in [Shot 1]): fully_preserved - "
                    f"{role} support retained."
                )
            continue
        # other refs → next Picture label with explicit duty (absorbs r2v_ref_prompt_clause)
        picture_n += 1
        pn = picture_n
        definitions.append(
            f"<Picture {pn}> is a {role} reference for [Shot 1] — {duty}."
        )
        retention.append(
            f"<Picture {pn}> ([Shot 1]): fully_preserved - {role} reference retained."
        )

    has_picture2 = any("<Picture 2>" in d for d in definitions)

    task_types = ["reference generation", "keyframe completion"]
    summary = (
        f"[{' + '.join(task_types)}] The target video animates <Subject 1> from <Picture 1> "
        f"for approximately {duration_sec:.1f} seconds with continuous motion and locked identity."
    )
    if has_picture2:
        summary += " Motion lands toward <Picture 2> as the end-pose reference."
    if subject_n >= 2:
        summary += " Secondary subject/style references stay fully preserved."

    detailed = _densify_ref_detailed(
        shot,
        style=style,
        size=size,
        subject=subject,
        action=action,
        cam=cam,
        dlg=dlg,
        duration_sec=duration_sec,
        has_picture2=has_picture2,
    )

    has_dlg = bool(dlg)
    return "\n".join(
        [
            "subject_definitions:",
            *definitions,
            "",
            "summary:",
            summary,
            "",
            "retention_analysis:",
            *retention,
            "",
            "detailed_description:",
            detailed,
            "",
            f"overall_soundscape: {_soundscape(shot, has_dlg=has_dlg)}",
            "",
            f"non_diegetic_music: {_music(shot)}",
            "",
        ]
    )


def compile_official_h3_prompt(
    shot: dict[str, Any],
    *,
    mode: str = "i2v",
    spec: dict[str, Any] | None = None,
    duration_sec: float | None = None,
    refs: list[dict[str, Any]] | None = None,
) -> str:
    """Compile a MiniMax-official prompt string for the given shot + mode."""
    official = map_official_mode(mode)
    dur = float(duration_sec) if duration_sec is not None else _dur(shot)
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    subject = str(dsl.get("subject") or shot.get("subject") or "the main character")
    size = _shot_size_phrase(shot)
    action = _action(shot)
    cam = _cam(shot)
    style = _style(shot, spec)
    tier = _tier(shot)
    dlg = _dlg(shot, subject_label=f"{subject}")

    if official == "Ref2VA":
        merged_refs = _merge_official_refs(shot, refs)
        return _build_ref2va(
            shot,
            style=style,
            size=size,
            subject=subject,
            action=action,
            cam=cam,
            dlg=dlg,
            duration_sec=dur,
            refs=merged_refs,
        )

    imd = _build_base_imd(
        shot,
        official=official,
        style=style,
        size=size,
        subject=subject,
        action=action,
        cam=cam,
        dlg=dlg,
        tier=tier,
        duration_sec=dur,
    )
    # Count shots for FL/L alignment last index
    last_n = max(1, len(re.findall(r"\[Shot \d+\]", imd)))
    align = _alignment_line(official, duration_sec=dur, last_shot_n=last_n)

    parts: list[str] = []
    if align:
        parts.extend([align, ""])
    parts.extend(
        [
            f"integrated_multimodal_description: {imd}",
            "",
            f"overall_soundscape: {_soundscape(shot, has_dlg=bool(dlg))}",
            "",
            f"non_diegetic_music: {_music(shot, spec)}",
        ]
    )
    return "\n".join(parts).strip() + "\n"


def validate_official_prompt(text: str, *, mode: str = "i2v") -> dict[str, Any]:
    """Structural check against official field requirements."""
    t = text or ""
    official = map_official_mode(mode)
    issues: list[str] = []

    if official == "Ref2VA":
        need = (
            "subject_definitions:",
            "summary:",
            "retention_analysis:",
            "detailed_description:",
            "overall_soundscape:",
            "non_diegetic_music:",
        )
    else:
        need = (
            "integrated_multimodal_description:",
            "overall_soundscape:",
            "non_diegetic_music:",
        )
    for k in need:
        if k not in t:
            issues.append(f"MISSING:{k}")

    if official == "I2VA":
        if "For the target video, at 0.00 seconds" not in t:
            issues.append("MISSING:I2VA_ALIGN_LINE")
        if "<Picture 1>" not in t:
            issues.append("MISSING:I2VA_PICTURE_ALIGN")
    if official == "FL2VA":
        if "How the reference pictures align" not in t:
            issues.append("MISSING:FL2VA_ALIGN_LINE")
        if "Picture 2" not in t:
            issues.append("MISSING:FL2VA_PICTURE2")
    if official == "L2VA":
        if "How the reference pictures align" not in t:
            issues.append("MISSING:L2VA_ALIGN_LINE")
    if official == "T2VA":
        # T2VA must not claim first-frame picture anchors
        if "For the target video, at 0.00 seconds" in t:
            issues.append("T2VA_HAS_I2VA_ALIGN")
        if re.search(r"shown in <Picture 1>", t):
            issues.append("T2VA_USES_PICTURE1_AS_SOURCE")
        if "<Picture 1>" in t and "L2VA" not in official:
            # Allow no pictures at all for pure T2VA
            issues.append("T2VA_UNEXPECTED_PICTURE_LABEL")

    if _LEGACY_TC_RE.search(t):
        issues.append("LEGACY_TIMECODE_MARKERS")
    if "=== 2V REFERENCE STAGE ===" in t:
        issues.append("LEGACY_2V_STAGE_HEADER")
    if re.search(r"(?i)vertical\s*9:16", t):
        issues.append("LEGACY_VERTICAL_PREFIX")

    return {
        "ok": not issues,
        "official_mode": official,
        "issues": issues,
        "has_dialogue_tag": "<d>" in t and "</d>" in t,
    }


def official_soft_validate() -> bool:
    """When true, validate failures warn instead of hard-fail (env escape)."""
    raw = os.environ.get("AIFILM_H3_OFFICIAL_SOFT", "0").strip().lower()
    return raw in {"1", "true", "yes", "on"}


__all__ = [
    "compile_official_h3_prompt",
    "map_official_mode",
    "official_soft_validate",
    "resolve_prompt_dialect",
    "validate_official_prompt",
]

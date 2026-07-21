#!/usr/bin/env python3
"""Multi-track voice layers for ai-film-grok.

Separates three content classes that used to get mashed into one nar / one mix:

1. **narration** (``nar``) — storyteller or dialogue; clean verbs, plate-timed TTS
2. **vocal_color** — 娇喘 / 色气语助词 / breathy reactions; own TTS stem + gain
3. **sound_cues** — 声景/物件描述 → SFX accents (not spoken as prose)

Tone tags (``tone_tags``) describe **performance manner** for still/I2V prompts
(e.g. breathy, teasing, dominant) — they are NOT mixed as loud VO.

Film-level gains (``voice_tracks`` or defaults). **Default = off**
(nar + BGM only; 娇喘语助 is opt-in):

```json
{
  "voice_tracks": {
    "enabled": false,
    "nar_gain": 1.32,
    "vocal_color_gain": 0.0,
    "native_audio_volume": 0.14,
    "sfx_bed_gain": 0.55,
    "auto_vocal_color": false
  }
}
```

Per-shot:

```json
{
  "nar": "她沉腰吃进。",
  "vocal_color": "嗯…啊…",
  "vocal_color_offset_sec": 1.2,
  "tone_tags": ["breathy", "teasing"],
  "sound_cues": ["leather", "breath", "impact"]
}
```
"""

from __future__ import annotations

from typing import Any

# Performance manner → still/I2V prompt language (not loudness)
TONE_TAG_PROMPTS: dict[str, str] = {
    "breathy": "soft breathy expression, parted lips, intimate breath",
    "teasing": "teasing half-lidded eyes, coy smirk",
    "dominant": "confident dominant gaze, controlled seduction",
    "needy": "needy flushed face, soft vulnerable look",
    "whisper": "lean-in whisper posture, intimate distance",
    "moan": "pleasure-soft open mouth, sensual reaction face",
    "afterglow": "soft afterglow smile, relaxed eyelids",
    "shy": "shy blush, averted then locking eyes",
    "hungry": "hungry fixed stare, heavy blush",
}

# heat / beat → short 语助词 (spoken color track only; keep very short for plate)
AUTO_VOCAL_COLOR: dict[str, list[str]] = {
    "setup": ["嗯…", "呵…"],
    "foreplay": ["哈…", "嗯啊…", "唔…"],
    "act": ["啊…嗯…", "哈啊…", "嗯…再…"],
    "climax": ["啊——", "嗯啊…", "哈啊…"],
    "afterglow": ["呼…", "嗯…", "呵…"],
    "bridge": ["…"],
}

# sound description tokens → sound_plan SFX kinds (breath already in SFX_KINDS)
SOUND_CUE_TO_SFX: dict[str, str] = {
    "breath": "breath",
    "breathe": "breath",
    "喘": "breath",
    "娇喘": "breath",
    "heartbeat": "heartbeat",
    "心跳": "heartbeat",
    "whoosh": "whoosh",
    "impact": "impact",
    "thud": "impact",
    "颠": "impact",
    "chime": "chime",
    "click": "chime",
    "leather": "generic",
    "seatbelt": "chime",
    "moan": "breath",
    "wet": "generic",
    "van": "whoosh",
    "neon": "generic",
}

DEFAULT_VOICE_TRACKS: dict[str, Any] = {
    # 2026-07-21: vocal_color (娇喘语助独立轨) 默认关闭 — 鸡肋；成片以 nar + BGM 为主
    "enabled": False,
    "nar_gain": None,  # fall through to vo_gain
    "vocal_color_gain": 0.0,
    "native_audio_volume": None,
    "sfx_bed_gain": 0.55,
    "auto_vocal_color": False,
    # color TTS slightly softer/slower than main VO when rate empty (only if explicitly re-enabled)
    "vocal_color_rate": "+0%",
    "vocal_color_pitch": "+2Hz",
}


class VoiceTracksError(ValueError):
    pass


def _heat_phase(shot: dict[str, Any]) -> str:
    hp = str(shot.get("heat_phase") or "").strip().lower()
    if hp:
        return hp
    fn = str(shot.get("dramatic_function") or "").strip().lower()
    if fn in {"hook", "approach"}:
        return "setup"
    if fn in {"sensory", "reaction"}:
        return "foreplay"
    if fn in {"action"}:
        return "act"
    if fn in {"afterglow", "resolution"}:
        return "afterglow"
    return "foreplay"


def normalize_tone_tags(raw: object) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        parts = [p.strip().lower() for p in raw.replace("，", ",").split(",") if p.strip()]
        return parts
    if isinstance(raw, (list, tuple)):
        out: list[str] = []
        for item in raw:
            s = str(item).strip().lower()
            if s:
                out.append(s)
        return out
    return []


def normalize_sound_cues(raw: object) -> list[str]:
    return normalize_tone_tags(raw)  # same list shape


def tone_tags_to_prompt(tags: list[str]) -> str:
    """English manner line for image_edit / I2V (performance, not SFX prose)."""
    bits: list[str] = []
    for t in tags:
        key = t.strip().lower()
        if key in TONE_TAG_PROMPTS:
            bits.append(TONE_TAG_PROMPTS[key])
        elif key:
            bits.append(key.replace("_", " "))
    if not bits:
        return ""
    return "Performance tone: " + "; ".join(bits)


def sound_cues_to_sfx_kinds(cues: list[str]) -> list[str]:
    kinds: list[str] = []
    for c in cues:
        k = SOUND_CUE_TO_SFX.get(c.strip().lower())
        if k and k not in kinds:
            kinds.append(k)
    return kinds


def resolve_voice_tracks(
    spec: dict[str, Any] | None,
    *,
    heat_scale: str | None = None,
) -> dict[str, Any]:
    """Merge film voice_tracks with defaults; disable auto color on soft heat."""
    base = dict(DEFAULT_VOICE_TRACKS)
    author = (spec or {}).get("voice_tracks") if isinstance(spec, dict) else None
    if isinstance(author, dict):
        for key in DEFAULT_VOICE_TRACKS:
            if key in author and author[key] is not None:
                base[key] = author[key]
    heat = str(heat_scale or (spec or {}).get("heat_scale") or "").strip().lower()
    # clamp gains
    for gkey in ("vocal_color_gain", "sfx_bed_gain"):
        try:
            base[gkey] = max(0.0, min(1.5, float(base[gkey])))
        except (TypeError, ValueError) as exc:
            raise VoiceTracksError(f"voice_tracks.{gkey} must be number") from exc
    base["enabled"] = bool(base.get("enabled", False))
    base["auto_vocal_color"] = bool(base.get("auto_vocal_color", False))
    # hard off: never emit color when disabled or gain 0
    if not base["enabled"] or float(base.get("vocal_color_gain") or 0) <= 0:
        base["enabled"] = False
        base["auto_vocal_color"] = False
        base["vocal_color_gain"] = 0.0
    return base


def pick_auto_vocal_color(shot: dict[str, Any], *, seed: int = 0) -> str:
    """Deterministic short color line from heat_phase."""
    phase = _heat_phase(shot)
    pool = AUTO_VOCAL_COLOR.get(phase) or AUTO_VOCAL_COLOR["foreplay"]
    if not pool:
        return ""
    sid = str(shot.get("id") or "")
    idx = (seed + sum(ord(c) for c in sid)) % len(pool)
    return pool[idx]


def resolve_shot_vocal_color(
    shot: dict[str, Any],
    *,
    policy: dict[str, Any],
    seed: int = 0,
) -> dict[str, Any]:
    """Return vocal_color payload for a shot (may be empty / disabled)."""
    if not policy.get("enabled"):
        return {"text": "", "offset_sec": 0.0, "source": "disabled", "gain": 0.0}

    explicit = str(shot.get("vocal_color") or shot.get("color_line") or "").strip()
    source = "author" if explicit else "none"
    text = explicit
    if not text and policy.get("auto_vocal_color"):
        # only auto on intimate phases when heat-ish tags present or heat_phase set
        phase = _heat_phase(shot)
        heat_ok = phase in {"foreplay", "act", "climax", "afterglow"} or bool(
            shot.get("heat_phase")
        )
        if heat_ok:
            text = pick_auto_vocal_color(shot, seed=seed)
            source = "auto"

    try:
        offset = float(shot.get("vocal_color_offset_sec"))
    except (TypeError, ValueError):
        offset = -1.0  # means auto: ~55% into plate

    try:
        gain = float(shot.get("vocal_color_gain"))
    except (TypeError, ValueError):
        gain = float(policy.get("vocal_color_gain") or 0.0)

    gain = max(0.0, min(1.5, gain))
    if not text:
        gain = 0.0

    return {
        "text": text,
        "offset_sec": offset,
        "source": source,
        "gain": gain,
        "rate": str(shot.get("vocal_color_rate") or policy.get("vocal_color_rate") or "+0%"),
        "pitch": str(shot.get("vocal_color_pitch") or policy.get("vocal_color_pitch") or "+2Hz"),
    }


def apply_voice_tracks_to_spec(spec: dict[str, Any], *, seed: int = 0) -> dict[str, Any]:
    """Mutate shots: fill tone_tags/sound_cues normalize + vocal_color when empty.

    Safe to call from write-spec. Does not invent long narration.
    """
    if not isinstance(spec, dict):
        raise VoiceTracksError("spec must be dict")
    policy = resolve_voice_tracks(spec)
    spec["voice_tracks"] = policy
    scenes = spec.get("scenes")
    if not isinstance(scenes, list):
        return {"voice_tracks": policy, "shots_with_color": 0}

    n_color = 0
    for scene in scenes:
        if not isinstance(scene, dict):
            continue
        for shot in scene.get("shots") or []:
            if not isinstance(shot, dict):
                continue
            tags = normalize_tone_tags(shot.get("tone_tags"))
            if tags:
                shot["tone_tags"] = tags
            cues = normalize_sound_cues(shot.get("sound_cues"))
            if cues:
                shot["sound_cues"] = cues
                # map to sfx for sound_plan consumers
                kinds = sound_cues_to_sfx_kinds(cues)
                if kinds:
                    shot["_sfx_kinds_from_cues"] = kinds
            color = resolve_shot_vocal_color(shot, policy=policy, seed=seed)
            shot["_vocal_color"] = color
            if color.get("text") and color.get("gain", 0) > 0:
                n_color += 1
                # keep author field mirrored when auto
                if color.get("source") == "auto" and not str(shot.get("vocal_color") or "").strip():
                    shot["vocal_color"] = color["text"]

    summary = {
        "voice_tracks": policy,
        "shots_with_color": n_color,
        "note": "nar=story; vocal_color=娇喘语助 independent gain; tone_tags=prompt manner; sound_cues=SFX",
    }
    spec["_voice_tracks_routing"] = summary
    return summary


def compute_color_offset_sec(
    *,
    offset_sec: float,
    plate_sec: float,
    color_dur: float,
    vo_dur: float | None = None,
) -> float:
    """Place color stem inside plate; default ~55% in, clamped so it fits."""
    plate = max(0.2, float(plate_sec))
    cdur = max(0.05, float(color_dur))
    if offset_sec is not None and float(offset_sec) >= 0:
        off = float(offset_sec)
    else:
        # prefer late-mid of VO if known, else 55% plate
        if vo_dur and vo_dur > 0.3:
            off = float(vo_dur) * 0.55
        else:
            off = plate * 0.55
    max_off = max(0.0, plate - cdur - 0.05)
    return max(0.0, min(off, max_off))

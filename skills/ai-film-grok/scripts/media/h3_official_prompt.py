"""Official MiniMax H3 prompt dialect compiler (h3-prompt-writing).

Default dialect **auto** after O3 canary 2026-08-07:
  dialogue → official; high-motion → legacy; else official.
Force: AIFILM_H3_PROMPT_DIALECT=official|legacy|auto
"""
from __future__ import annotations
import os, re
from typing import Any

_OFF = frozenset({"official", "h3_official", "minimax", "native", "v2"})
_LEG = frozenset({"legacy", "timeline", "temporal", "flat", "spine", "v1", "old", "h3_timeline"})
_AUTO = frozenset({"auto", "hybrid", "smart", "canary", "v3"})


def resolve_prompt_dialect(shot=None, *, explicit=None):
    if explicit is not None and str(explicit).strip():
        raw = str(explicit).strip().lower()
    else:
        sh = shot if isinstance(shot, dict) else {}
        dsl = sh.get("dsl") if isinstance(sh.get("dsl"), dict) else {}
        raw = str(
            dsl.get("prompt_dialect") or dsl.get("prompt_format")
            or sh.get("prompt_dialect") or sh.get("prompt_format")
            or os.environ.get("AIFILM_H3_PROMPT_DIALECT") or "auto"
        ).strip().lower()
    if raw in _OFF:
        return "official"
    if raw in _LEG:
        return "legacy"
    return _auto_dialect_for_shot(shot if isinstance(shot, dict) else {})


def _auto_dialect_for_shot(shot):
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
        tier = str(dsl.get("prompt_tier") or shot.get("prompt_tier") or "medium").lower()
    if has_dlg:
        return "official"
    if tier == "high":
        return "legacy"
    return "official"


def map_official_mode(mode: str) -> str:
    m = (mode or "i2v").strip().lower()
    if m in {"t2v", "text_to_video", "text-to-video"}: return "T2VA"
    if m in {"r2v", "ref2v", "reference", "reference_to_video", "ref2va"}: return "Ref2VA"
    if m in {"flf", "first_last", "first_last_frame", "i2v_flf", "fl2va"}: return "FL2VA"
    if m in {"l2v", "l2va", "last_frame", "last_only"}: return "L2VA"
    return "I2VA"


def _dur(shot, default=5.0):
    try: return max(2.0, min(8.0, float(shot.get("duration_sec") or default)))
    except Exception: return default


def _tier(shot):
    try:
        from motion_prompt_spine import motion_tier_for
        return str(motion_tier_for(shot) or "medium").lower()
    except Exception:
        dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
        return str(dsl.get("prompt_tier") or shot.get("prompt_tier") or "medium").lower()


def _dlg(shot):
    try:
        from motion_prompt_spine import shot_screen_mode, spoken_dialogue_text
        d, sc = spoken_dialogue_text(shot), shot_screen_mode(shot)
    except Exception:
        d, sc = "", ""
        for c in shot.get("audio_cues") or []:
            if isinstance(c, dict) and str(c.get("spoken_text") or "").strip():
                d = str(c["spoken_text"]).strip(); sc = str(c.get("screen_mode") or ""); break
    if not d: return ""
    lang = "Mandarin" if re.search(r"[\u4e00-\u9fff]", d) else "English"
    tag = f"<d>[{lang}] {d}</d>"
    if sc == "off_camera":
        return f"the visible character with a clear natural voice (S1) says in an off-screen voiceover: {tag} while the on-screen lips remain completely closed"
    return f"the visible character with a clear natural voice (S1) says: {tag} with clear jaw open-close and visible lip shapes on each syllable"


def _action(shot):
    try:
        from motion_prompt_spine import dsl_action_parts
        parts = dsl_action_parts(shot)
    except Exception:
        dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
        parts = [str(dsl.get(k) or "").strip() for k in ("action", "motion", "visible_change") if str(dsl.get(k) or "").strip()]
    tier = _tier(shot)
    base = "; ".join(parts) if parts else ""
    if tier == "high":
        densify = "large visible pose and body torque every half-second; weight shifts, hands re-grip, fabric and hair snap with inertia; silhouette changes continuously — never a frozen portrait"
        return f"{base}; {densify}" if base else densify
    if tier == "soft":
        micro = "continuous micro-life every half-second: soft blinks, breath lifts the chest, tiny head sway and hair drift; never freeze into a still photo"
        return f"{base}; {micro}" if base else micro
    if base: return base
    if _dlg(shot):
        return "the subject begins from the start-frame pose, articulates speech with natural head micro-motion, and settles into a clear end expression"
    return "continuous natural body motion from the start frame to a clear end pose"


def _cam(shot):
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    raw = str(dsl.get("camera_prompt") or "")
    tier = _tier(shot)
    if re.search(r"lock|static", raw, re.I) or (tier == "soft" and not re.search(r"push|pan|truck", raw, re.I)):
        return "The camera holds a static shot"
    if re.search(r"handheld|aggressive|whip", raw, re.I) or tier == "high":
        return "The camera shakes strongly with large amplitude at fast speed"
    if re.search(r"push", raw, re.I):
        return "The camera pushes in with small amplitude at slow speed"
    if tier == "soft":
        return "The camera holds a static shot"
    return "The camera pushes in with small amplitude at slow speed"


def _style(shot, spec=None):
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    blob = " ".join(str(x) for x in (dsl.get("style"), shot.get("style"), (spec or {}).get("genre")) if x).lower()
    if any(k in blob for k in ("cel", "anime", "manhua", "manga", "2d")):
        return "2D-animated, medium cel-anime"
    return "Cinematic, 2D-animated"


def _soundscape(shot, *, has_dlg):
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    custom = str(dsl.get("soundscape") or dsl.get("ambience") or "").strip()
    if custom: return custom
    tier = _tier(shot)
    if has_dlg:
        return "Natural room tone and soft fabric movement continue under the spoken line, with subtle body-shift foley matched to visible motion."
    if tier == "high":
        return "Energetic diegetic ambience and hard fabric/body impact sounds follow the visible action; cloth snaps, weight thuds, and hair whip stay continuous."
    if tier == "soft":
        return "Soft ambient room tone and gentle air movement; micro fabric rustle only."
    return "Natural diegetic ambience and soft foley matched to the visible action continue throughout the clip."


def compile_official_h3_prompt(shot, *, mode="i2v", spec=None, duration_sec=None):
    official = map_official_mode(mode)
    dur = float(duration_sec) if duration_sec is not None else _dur(shot)
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    subject = str(dsl.get("subject") or shot.get("subject") or "the main character")
    size_tok = str(shot.get("shot_size") or "").lower()
    size = "a close-up" if size_tok in {"cu", "ecu", "close", "closeup", "close_up"} else "a medium shot"
    action, cam, dlg, style, tier = _action(shot), _cam(shot), _dlg(shot), _style(shot, spec), _tier(shot)

    if official == "Ref2VA":
        body = f"[Shot 1] {size} opens on <Subject 1> from <Picture 1>. {cam} as {action}."
        if dlg:
            tail = dlg.split("(S1)", 1)[-1] if "(S1)" in dlg else f" {dlg}"
            body += f" <Subject 1> (S1){tail}"
            if not body.endswith("."): body += "."
        return "\n".join([
            "subject_definitions:",
            f"<Subject 1> is {subject} in <Picture 1>, with locked face identity, hair, wardrobe.",
            "", "summary:",
            f"[reference generation + keyframe completion] Animate <Subject 1> from <Picture 1> for ~{dur:.1f}s.",
            "", "retention_analysis:",
            "<Subject 1> (appears in [Shot 1]): fully_preserved - identity retained.",
            "<Picture 1> ([Shot 1] first frame): fully_preserved - opening anchor.",
            "", "detailed_description:",
            f"The target video uses a {style} look. {body} Ends on a clear pose.",
            "", f"overall_soundscape: {_soundscape(shot, has_dlg=bool(dlg))}",
            "", "non_diegetic_music: N/A", "",
        ])

    imd = f"[Shot 1] {style}, {size} frames {subject} shown in <Picture 1>, preserving appearance, clothing, hair, face identity. "
    if official == "I2VA":
        imd += "The sequence develops forward from the first-frame anchors in <Picture 1>. "
    elif official == "FL2VA":
        imd += "Motion interpolates continuously from Picture 1 toward Picture 2 at the end of the shot. "
    if tier == "high":
        imd += "HIGH-ENERGY continuous action path: "
    imd += f"{cam} as {action}. "
    imd += (dlg + ". ") if dlg else "No on-screen speech; diegetic physical sounds follow the visible events. "
    imd += "The final moments resolve into a clear ending pose and composition without freezing mid-action."
    wardrobe = str(shot.get("wardrobe_state") or "").strip().lower()
    if wardrobe in {"bare", "undressed", "nude"}:
        imd += " Keep first-frame clothing state; never re-dress after undress."

    align = None
    if official == "I2VA":
        align = "For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced."
    elif official == "FL2VA":
        align = f"How the reference pictures align with the target video — Picture 1 (from Shot 1) aligns with the 0.00-second mark of the target video; Picture 2 (from Shot 1) aligns with the {dur:.2f}-second mark of the target video."
    elif official == "L2VA":
        align = f"How the reference pictures align with the target video — <Picture 1> (from [Shot 1]) aligns with the {dur:.2f}-second mark of the target video."

    parts = []
    if align: parts.extend([align, ""])
    parts.extend([
        f"integrated_multimodal_description: {imd}", "",
        f"overall_soundscape: {_soundscape(shot, has_dlg=bool(dlg))}", "",
        "non_diegetic_music: N/A",
    ])
    return "\n".join(parts).strip() + "\n"


def validate_official_prompt(text, *, mode="i2v"):
    t = text or ""
    official = map_official_mode(mode)
    issues = []
    need = ("subject_definitions:", "detailed_description:", "overall_soundscape:", "non_diegetic_music:") if official == "Ref2VA" else ("integrated_multimodal_description:", "overall_soundscape:", "non_diegetic_music:")
    for k in need:
        if k not in t: issues.append(f"MISSING:{k}")
    if official == "I2VA" and "<Picture 1>" not in t: issues.append("MISSING:I2VA_PICTURE_ALIGN")
    if re.search(r"\[\d+(?:\.\d+)?s\s*-\s*\d+(?:\.\d+)?s\]", t): issues.append("LEGACY_TIMECODE_MARKERS")
    return {"ok": not issues, "official_mode": official, "issues": issues, "has_dialogue_tag": "<d>" in t and "</d>" in t}


__all__ = ["compile_official_h3_prompt", "map_official_mode", "resolve_prompt_dialect", "validate_official_prompt"]

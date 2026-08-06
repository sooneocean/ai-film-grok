#!/usr/bin/env python3
"""Idle-gated H3 T2V/I2V/R2V(/FLF) param+prompt combo evaluation.

Pure matrix + scorer are unit-testable without Comfy. GPU I/O goes only through
shipped run_h3_shot / submission_capacity / free_memory.

Lanes: hero_identity_lock · high_motion_energy · dialogue_mouth_energy · faceless_env
"""
from __future__ import annotations

import json
import shutil
import subprocess
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DEFAULT_SEED = 20260805
DEFAULT_STEPS = 20
VERDICT_KIND = "h3-combo-verdict"

PROMPT_FAMILIES: dict[str, dict[str, Any]] = {
    "soft_portrait": {
        "lane_tags": ["hero_identity_lock"],
        "shot_role": "hero",
        "heat_phase": "setup",
        "wardrobe_state": "clothed",
        "prompt_tier": "soft",
        "nar": "soft natural portrait, subtle breathing and gentle head turn, warm indoor light",
        "dsl": {
            "action": "subject holds eye contact with slight smile",
            "motion": "slow push-in, hair micro-motion",
            "visible_change": "expression softens, shoulders rise with breath",
            "camera_prompt": "medium slow push-in",
            "environment": "soft indoor light drift; hair micro-movement",
        },
        # author_prompt: optional override; prepare_eval_root prefers Layer-4 compile.
        "author_prompt": None,
        "prompt_format": "timeline",
    },
    "high_motion": {
        "lane_tags": ["high_motion_energy", "hero_identity_lock"],
        "shot_role": "hero",
        "heat_phase": "act",
        "wardrobe_state": "clothed",
        "prompt_tier": "high",
        "nar": "high energy body motion, strong physical performance",
        "dsl": {
            "action": "body rocks with vigorous rhythm, hands grip fabric, weight shifts hard",
            "motion": "aggressive handheld push-in and lateral drift, hair and clothes whip",
            "visible_change": "pose changes clearly every second, large motion amplitude",
            "camera_prompt": "aggressive handheld push-in and lateral drift",
            "environment": "hair and clothes whip; room air and fabric snap with inertia",
        },
        "author_prompt": None,
        "prompt_format": "timeline",
    },
    "dialogue_mandarin": {
        "lane_tags": ["dialogue_mouth_energy", "hero_identity_lock"],
        "shot_role": "hero",
        "heat_phase": "act",
        "wardrobe_state": "clothed",
        "prompt_tier": "medium",
        "screen_mode": "on_camera",
        "shot_size": "cu",
        "nar": "close-up speaking performance",
        "dsl": {
            "action": "character faces camera and speaks clearly",
            "motion": "subtle head motion while talking, mouth articulates",
            "visible_change": "lips form Mandarin syllables, expression engages",
            "camera_prompt": "locked 85mm close-up, micro push only",
            "environment": "soft room light micro-shifts; quiet ambience",
        },
        "audio_cues": [
            {
                "kind": "voice",
                "line_type": "dialogue",
                "speaker": "hero",
                "spoken_text": "过来，靠近一点，别停。",
                "screen_mode": "on_camera",
            }
        ],
        "author_prompt": None,
        "prompt_format": "timeline",
    },
    "env_no_face": {
        "lane_tags": ["faceless_env"],
        "shot_role": "env",
        "heat_phase": "setup",
        "wardrobe_state": "clothed",
        "prompt_tier": "medium",
        "nar": "empty environment atmosphere plate, no people",
        "dsl": {
            "action": "wind moves curtains and foliage, light shifts on walls",
            "motion": "slow lateral drift across empty room",
            "visible_change": "shadows and fabric move; no faces appear",
            "camera_prompt": "slow lateral drift",
            "environment": "curtains and foliage micro-motion; window light shifts",
        },
        "author_prompt": None,
        "prompt_format": "timeline",
    },
    "soft_portrait_alive": {
        "lane_tags": ["hero_identity_lock"],
        "shot_role": "hero",
        "heat_phase": "setup",
        "wardrobe_state": "clothed",
        "prompt_tier": "soft",
        "nar": "alive portrait: continuous micro-life, never freeze, keep identity",
        "dsl": {
            "action": "eyes track camera with soft blinks, breath lifts chest continuously",
            "motion": "tiny head sway and hair drift; locked identity, no morph",
            "visible_change": "every half-second a small natural micro-change; never a still photo",
            "camera_prompt": "medium slow push-in, identity lock",
            "environment": "hair micro-drift and fabric settle",
        },
        "author_prompt": None,
        "prompt_format": "timeline",
    },
    "high_motion_max": {
        "lane_tags": ["high_motion_energy", "hero_identity_lock"],
        "shot_role": "hero",
        "heat_phase": "act",
        "wardrobe_state": "clothed",
        "prompt_tier": "high",
        "nar": "maximum body kinetic energy with identity lock",
        "dsl": {
            "action": (
                "full-body weight shifts and torso torque every 0.5s; hands re-grip; "
                "hips and shoulders counter-rotate hard"
            ),
            "motion": (
                "aggressive handheld push-in plus lateral whip; hair and clothes snap with inertia"
            ),
            "visible_change": (
                "pose silhouette changes large every half second; high optical flow; not micro-breath"
            ),
            "camera_prompt": "aggressive handheld push-in plus lateral whip",
            "environment": "hair and clothes snap with inertia; dust and fabric thrash",
        },
        "author_prompt": None,
        "prompt_format": "timeline",
    },
    "dialogue_mouth_max": {
        "lane_tags": ["dialogue_mouth_energy", "hero_identity_lock"],
        "shot_role": "hero",
        "heat_phase": "build",
        "wardrobe_state": "clothed",
        "prompt_tier": "medium",
        "dramatic_function": "dialogue",
        "screen_mode": "on_camera",
        "shot_size": "cu",
        "nar": "close-up Mandarin speech with strong visible mouth performance",
        "dsl": {
            "action": "face camera and speak with clear jaw open-close each syllable",
            "motion": "cheeks and jaw move; brows engage; tiny head nods with speech rhythm",
            "visible_change": "lips and jaw articulate every Mandarin syllable; mouth energy high",
            "camera_prompt": "locked ECU mouth-priority close-up",
            "environment": "soft key light micro-shift on face",
            "timeline_events": [
                "jaw opens on first Mandarin syllables with clear lip shapes",
                "keeps articulating mid-line with cheek and brow engagement",
                "finishes line and holds expressive end mouth shape",
            ],
        },
        "audio_cues": [
            {
                "kind": "voice",
                "line_type": "dialogue",
                "speaker": "hero",
                "spoken_text": "过来，靠近一点，别停。",
                "screen_mode": "on_camera",
            }
        ],
        "author_prompt": None,
        "prompt_format": "timeline",
    },
    "env_kinetic": {
        "lane_tags": ["faceless_env"],
        "shot_role": "env",
        "heat_phase": "setup",
        "wardrobe_state": "clothed",
        "prompt_tier": "high",
        "nar": "kinetic empty environment: wind, light, parallax, no people",
        "dsl": {
            "action": "strong wind billows curtains; foliage thrash; light shafts sweep walls",
            "motion": "forward dolly with parallax depth through empty room",
            "visible_change": "shadows and fabric move large every second; no faces appear",
            "camera_prompt": "forward dolly with clear parallax depth",
            "environment": "curtains thrash; foliage thrash; dust motes; light shafts sweep",
        },
        "author_prompt": None,
        "prompt_format": "timeline",
    },
    # Flat-paragraph baselines for timeline A/B (dsl.prompt_format=flat).
    "high_motion_flat": {
        "lane_tags": ["high_motion_energy", "hero_identity_lock", "timeline_ab_flat"],
        "shot_role": "hero",
        "heat_phase": "act",
        "wardrobe_state": "clothed",
        "prompt_tier": "high",
        "nar": "high energy body motion flat-paragraph baseline",
        "dsl": {
            "action": "body rocks with vigorous rhythm, hands grip fabric, weight shifts hard",
            "motion": "aggressive handheld push-in and lateral drift, hair and clothes whip",
            "visible_change": "pose changes clearly every second, large motion amplitude",
            "prompt_format": "flat",
        },
        "prompt_format": "flat",
        "author_prompt": (
            "Vertical 9:16. Animate the start frame with medium cel-anime style lock. "
            "Keep identity and wardrobe fixed. HIGH MOTION priority: large visible pose/body "
            "change every second; avoid frozen portrait or micro-breath-only. Body rocks with "
            "vigorous rhythm, hands grip fabric, weight shifts hard. Aggressive handheld "
            "push-in and lateral drift; hair and clothes whip. Pose changes clearly every "
            "second with large motion amplitude. No morphing, no face swap, no extra people."
        ),
    },
    "dialogue_mouth_flat": {
        "lane_tags": ["dialogue_mouth_energy", "hero_identity_lock", "timeline_ab_flat"],
        "shot_role": "hero",
        "heat_phase": "act",
        "wardrobe_state": "clothed",
        "prompt_tier": "medium",
        "screen_mode": "on_camera",
        "shot_size": "cu",
        "nar": "close-up Mandarin speech flat-paragraph baseline",
        "dsl": {
            "action": "face camera and speak with clear jaw open-close each syllable",
            "motion": "cheeks and jaw move; brows engage; tiny head nods with speech rhythm",
            "visible_change": "lips and jaw articulate every Mandarin syllable; mouth energy high",
            "prompt_format": "flat",
        },
        "prompt_format": "flat",
        "audio_cues": [
            {
                "kind": "voice",
                "line_type": "dialogue",
                "speaker": "hero",
                "spoken_text": "过来，靠近一点，别停。",
                "screen_mode": "on_camera",
            }
        ],
        "author_prompt": (
            "Vertical 9:16 close-up. Animate the start frame; keep exact identity fixed. "
            "STRONG LIP SYNC: jaw opens and closes clearly on each Mandarin syllable; cheeks and "
            "mouth corners move; brows engage; tiny head nods on speech rhythm. "
            "line: 「过来，靠近一点，别停。」 "
            "Mouth region must show high visible change while face identity stays locked. "
            "No morphing, no face swap, no frozen mouth."
        ),
    },
}

DEFAULT_COMBO_ORDER: list[dict[str, Any]] = [
    {"combo_id": "soft_i2v", "mode": "i2v", "family": "soft_portrait", "shot_id": "s_soft"},
    {"combo_id": "soft_r2v", "mode": "r2v", "family": "soft_portrait", "shot_id": "s_soft"},
    {"combo_id": "high_i2v", "mode": "i2v", "family": "high_motion", "shot_id": "s_hi"},
    {"combo_id": "high_r2v", "mode": "r2v", "family": "high_motion", "shot_id": "s_hi"},
    {"combo_id": "dlg_i2v", "mode": "i2v", "family": "dialogue_mandarin", "shot_id": "s_dlg"},
    {"combo_id": "dlg_r2v", "mode": "r2v", "family": "dialogue_mandarin", "shot_id": "s_dlg"},
    {"combo_id": "env_t2v", "mode": "t2v", "family": "env_no_face", "shot_id": "s_env"},
    {
        "combo_id": "high_flf",
        "mode": "flf",
        "family": "high_motion",
        "shot_id": "s_hi",
        "requires_last": True,
    },
]

# Round-2: optimized prompt families (beat R1 soft freeze / high gap / mouth soft / env soft)
R2_COMBO_ORDER: list[dict[str, Any]] = [
    {"combo_id": "r2_soft_alive_i2v", "mode": "i2v", "family": "soft_portrait_alive", "shot_id": "s_soft2"},
    {"combo_id": "r2_high_max_i2v", "mode": "i2v", "family": "high_motion_max", "shot_id": "s_hi2"},
    {"combo_id": "r2_high_max_r2v", "mode": "r2v", "family": "high_motion_max", "shot_id": "s_hi2"},
    {"combo_id": "r2_dlg_mouth_i2v", "mode": "i2v", "family": "dialogue_mouth_max", "shot_id": "s_dlg2"},
    {"combo_id": "r2_dlg_mouth_r2v", "mode": "r2v", "family": "dialogue_mouth_max", "shot_id": "s_dlg2"},
    {"combo_id": "r2_env_kinetic_t2v", "mode": "t2v", "family": "env_kinetic", "shot_id": "s_env2"},
]

# Round-3: flat-paragraph vs Layer-4 timeline A/B (same still / seed / steps).
R3_TIMELINE_AB_ORDER: list[dict[str, Any]] = [
    {
        "combo_id": "ab_high_flat_i2v",
        "mode": "i2v",
        "family": "high_motion_flat",
        "shot_id": "s_ab_hi_flat",
        "lane_tags": ["high_motion_energy", "timeline_ab_flat"],
    },
    {
        "combo_id": "ab_high_tl_i2v",
        "mode": "i2v",
        "family": "high_motion_max",
        "shot_id": "s_ab_hi_tl",
        "lane_tags": ["high_motion_energy", "timeline_ab_timeline"],
    },
    {
        "combo_id": "ab_high_flat_r2v",
        "mode": "r2v",
        "family": "high_motion_flat",
        "shot_id": "s_ab_hi_flat",
        "lane_tags": ["high_motion_energy", "timeline_ab_flat"],
    },
    {
        "combo_id": "ab_high_tl_r2v",
        "mode": "r2v",
        "family": "high_motion_max",
        "shot_id": "s_ab_hi_tl",
        "lane_tags": ["high_motion_energy", "timeline_ab_timeline"],
    },
    {
        "combo_id": "ab_dlg_flat_i2v",
        "mode": "i2v",
        "family": "dialogue_mouth_flat",
        "shot_id": "s_ab_dlg_flat",
        "lane_tags": ["dialogue_mouth_energy", "timeline_ab_flat"],
    },
    {
        "combo_id": "ab_dlg_tl_i2v",
        "mode": "i2v",
        "family": "dialogue_mouth_max",
        "shot_id": "s_ab_dlg_tl",
        "lane_tags": ["dialogue_mouth_energy", "timeline_ab_timeline"],
    },
]

# Round-4: post-R3 policy — fixed MOUTH ENERGY timeline + retry failed flat R2V +
# dialogue R2V stress + soft identity timeline smoke.
R4_POST_FIX_ORDER: list[dict[str, Any]] = [
    {
        "combo_id": "r4_high_tl_i2v",
        "mode": "i2v",
        "family": "high_motion_max",
        "shot_id": "s_r4_hi",
        "lane_tags": ["high_motion_energy", "timeline_ab_timeline"],
    },
    {
        "combo_id": "r4_high_tl_r2v",
        "mode": "r2v",
        "family": "high_motion_max",
        "shot_id": "s_r4_hi",
        "lane_tags": ["high_motion_energy", "timeline_ab_timeline"],
    },
    {
        "combo_id": "r4_high_flat_r2v",
        "mode": "r2v",
        "family": "high_motion_flat",
        "shot_id": "s_r4_hi_flat",
        "lane_tags": ["high_motion_energy", "timeline_ab_flat"],
    },
    {
        "combo_id": "r4_dlg_flat_i2v",
        "mode": "i2v",
        "family": "dialogue_mouth_flat",
        "shot_id": "s_r4_dlg_flat",
        "lane_tags": ["dialogue_mouth_energy", "timeline_ab_flat"],
    },
    {
        "combo_id": "r4_dlg_tl_i2v",
        "mode": "i2v",
        "family": "dialogue_mouth_max",
        "shot_id": "s_r4_dlg_tl",
        "lane_tags": ["dialogue_mouth_energy", "timeline_ab_timeline"],
    },
    {
        "combo_id": "r4_dlg_tl_r2v",
        "mode": "r2v",
        "family": "dialogue_mouth_max",
        "shot_id": "s_r4_dlg_tl",
        "lane_tags": ["dialogue_mouth_energy", "timeline_ab_timeline"],
    },
    {
        "combo_id": "r4_soft_tl_i2v",
        "mode": "i2v",
        "family": "soft_portrait_alive",
        "shot_id": "s_r4_soft",
        "lane_tags": ["hero_identity_lock", "timeline_ab_timeline"],
    },
]



@dataclass
class ComboSpec:
    combo_id: str
    mode: str
    family: str
    shot_id: str
    seed: int = DEFAULT_SEED
    steps: int | str = DEFAULT_STEPS
    requires_last: bool = False
    lane_tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_combo_matrix(
    *,
    seed: int = DEFAULT_SEED,
    include_flf: bool = True,
    order: list[dict[str, Any]] | None = None,
    round: int = 1,
) -> list[ComboSpec]:
    if order is not None:
        rows = order
    elif int(round) >= 4:
        rows = list(R4_POST_FIX_ORDER)
    elif int(round) >= 3:
        rows = list(R3_TIMELINE_AB_ORDER)
    elif int(round) >= 2:
        rows = list(R2_COMBO_ORDER)
    else:
        rows = list(DEFAULT_COMBO_ORDER)
    out: list[ComboSpec] = []
    for raw in rows:
        mode = str(raw["mode"]).lower()
        family = str(raw["family"])
        if not include_flf and mode == "flf":
            continue
        fam = PROMPT_FAMILIES.get(family) or {}
        tags = list(raw.get("lane_tags") or fam.get("lane_tags") or [])
        out.append(
            ComboSpec(
                combo_id=str(raw["combo_id"]),
                mode=mode,
                family=family,
                shot_id=str(raw.get("shot_id") or f"s_{raw['combo_id']}"),
                seed=int(raw.get("seed") or seed),
                steps=raw.get("steps", DEFAULT_STEPS),
                requires_last=bool(raw.get("requires_last")),
                lane_tags=tags,
            )
        )
    return out


def shot_dict_for_family(family: str, shot_id: str) -> dict[str, Any]:
    fam = PROMPT_FAMILIES[family]
    heat = str(fam.get("heat_phase") or "setup")
    # Infer DF from heat so timeline header is not generic "beat".
    if heat in {"act", "climax"}:
        df = "action"
    elif heat in {"afterglow"}:
        df = "afterglow"
    else:
        df = "setup" if fam.get("shot_role") == "env" else "approach"
    shot: dict[str, Any] = {
        "id": shot_id,
        "shot_role": fam.get("shot_role", "hero"),
        "heat_phase": heat,
        "wardrobe_state": fam.get("wardrobe_state", "clothed"),
        "dramatic_function": fam.get("dramatic_function") or df,
        "nar": fam.get("nar", ""),
        "dsl": dict(fam.get("dsl") or {}),
    }
    if fam.get("screen_mode"):
        shot["screen_mode"] = fam["screen_mode"]
    if fam.get("shot_size"):
        shot["shot_size"] = fam["shot_size"]
    if fam.get("prompt_tier"):
        shot["prompt_tier"] = fam["prompt_tier"]
        shot.setdefault("dsl", {})["prompt_tier"] = fam["prompt_tier"]
    if fam.get("audio_cues"):
        shot["audio_cues"] = list(fam["audio_cues"])
    # prompt_format: timeline (default 5090) | flat (A/B baseline)
    pfmt = str(fam.get("prompt_format") or shot["dsl"].get("prompt_format") or "timeline").strip()
    shot["prompt_format"] = pfmt
    shot.setdefault("dsl", {})["prompt_format"] = pfmt
    return shot


def compile_family_author_prompt(
    family: str,
    *,
    shot_id: str | None = None,
    duration_sec: float = 5.0,
    mode: str = "i2v",
) -> str:
    """Compile Layer-4 timeline (or flat override) author prompt for a combo family."""
    fam = PROMPT_FAMILIES[family]
    pfmt = str(fam.get("prompt_format") or "timeline").strip().lower()
    if pfmt == "flat" and fam.get("author_prompt"):
        return str(fam["author_prompt"]).strip()
    if fam.get("author_prompt"):
        return str(fam["author_prompt"]).strip()
    from motion_prompt_spine import build_h3_temporal_prompt

    shot = shot_dict_for_family(family, shot_id or f"s_{family}")
    return build_h3_temporal_prompt(
        {}, shot, mode=mode, duration_sec=float(duration_sec)
    ).strip()


def family_apply_enabled() -> bool:
    """Production path applies combo family DSL fill. Escape: AIFILM_H3_FAMILY_APPLY=0."""
    import os

    raw = os.environ.get("AIFILM_H3_FAMILY_APPLY", "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


_DSL_FILL_KEYS = (
    "action",
    "motion",
    "visible_change",
    "camera_prompt",
    "environment",
    "timeline_events",
    "prompt_tier",
    "prompt_format",
)


def apply_combo_family_to_shot(
    shot: dict[str, Any],
    family_id: str | None,
    *,
    force: bool = False,
) -> dict[str, Any]:
    """Merge winning prompt-family defaults into a production shot (fill holes only).

    Does **not** overwrite non-empty author/DSL fields unless ``force=True``.
    Used so registry ``prompt_family`` actually changes compiled H3 prompts
    (plan.combo_prompt_family was annotate-only before this).
    """
    if not family_id or not isinstance(shot, dict):
        return shot if isinstance(shot, dict) else {}
    fam = PROMPT_FAMILIES.get(str(family_id).strip())
    if not isinstance(fam, dict):
        return dict(shot)

    out = dict(shot)
    # Only motion-tier / framing helpers at top level — never steal story beat (nar/DF).
    for key, fam_key in (
        ("prompt_tier", "prompt_tier"),
        ("screen_mode", "screen_mode"),
        ("shot_size", "shot_size"),
    ):
        if fam_key not in fam:
            continue
        cur = out.get(key)
        empty = cur is None or (isinstance(cur, str) and not str(cur).strip())
        if force or empty:
            out[key] = fam[fam_key]
    # prompt_format only when force (production 5090 already defaults timeline)
    if force and fam.get("prompt_format"):
        out["prompt_format"] = fam["prompt_format"]

    # Do not inject eval-only audio_cues into live dialogue shots (would overwrite lines).
    if force and fam.get("audio_cues") and not out.get("audio_cues"):
        out["audio_cues"] = list(fam["audio_cues"])

    dsl_in = out.get("dsl") if isinstance(out.get("dsl"), dict) else {}
    dsl = dict(dsl_in)
    fam_dsl = fam.get("dsl") if isinstance(fam.get("dsl"), dict) else {}
    for key in _DSL_FILL_KEYS:
        if key not in fam_dsl and key not in fam:
            continue
        src = fam_dsl.get(key) if key in fam_dsl else fam.get(key)
        if src is None or src == "":
            continue
        cur = dsl.get(key)
        empty = (
            cur is None
            or cur == ""
            or (isinstance(cur, str) and not cur.strip())
            or (isinstance(cur, list) and len(cur) == 0)
        )
        if force or empty:
            dsl[key] = list(src) if isinstance(src, list) else src
    if fam.get("prompt_tier") and (force or not dsl.get("prompt_tier")):
        dsl["prompt_tier"] = fam["prompt_tier"]
    if force and fam.get("prompt_format") and not dsl.get("prompt_format"):
        dsl["prompt_format"] = fam["prompt_format"]
    out["dsl"] = dsl
    out["_combo_prompt_family_applied"] = str(family_id).strip()
    return out


def resolve_prompt_family_for_shot(
    shot: dict[str, Any],
    *,
    intent: dict[str, Any] | None = None,
    has_still: bool | None = None,
    family_override: str | None = None,
) -> str | None:
    """Pick registry prompt_family for a live shot (lane → winners)."""
    if family_override and str(family_override).strip():
        fid = str(family_override).strip()
        return fid if fid in PROMPT_FAMILIES else fid
    try:
        from h3_mode import infer_combo_lane

        still_flag = bool(has_still) if has_still is not None else bool(
            shot.get("still_path") or shot.get("has_still")
        )
        role = str(
            (intent or {}).get("shot_role") if intent else None
            or shot.get("shot_role")
            or "hero"
        ).strip().lower()
        if not still_flag and role in {"hero", "insert", ""}:
            still_flag = True
        lane = infer_combo_lane(shot, intent=intent, has_still=still_flag)
    except Exception:
        lane = None
    if not lane:
        raw = (
            (shot.get("dsl") or {}).get("prompt_family")
            if isinstance(shot.get("dsl"), dict)
            else None
        ) or shot.get("prompt_family") or shot.get("combo_prompt_family")
        if raw and str(raw).strip() in PROMPT_FAMILIES:
            return str(raw).strip()
        return None
    data = load_combo_winners() or {}
    lanes = data.get("lanes") if isinstance(data.get("lanes"), dict) else {}
    entry = lanes.get(lane) if isinstance(lanes.get(lane), dict) else {}
    family = (entry or {}).get("prompt_family")
    if family and str(family).strip():
        return str(family).strip()
    return None


def build_eval_film_spec(combos: list[ComboSpec] | None = None) -> dict[str, Any]:
    combos = combos or build_combo_matrix()
    shots_by_id: dict[str, dict[str, Any]] = {}
    for c in combos:
        if c.shot_id not in shots_by_id:
            shots_by_id[c.shot_id] = shot_dict_for_family(c.family, c.shot_id)
    # genre != adult: variety preflight meat floors would block 5s pilot A/B grids.
    return {
        "title": "h3-combo-eval",
        "genre": "drama",
        "aspect_ratio": "9:16",
        "vo_mode": "storyteller",
        "tts_backend": "edge",
        "i2v_provider": "auto",
        "_i2v_profile": "h3_primary",
        "h3": {
            "enabled": True,
            "stage": "pilot",
            "max_duration_sec": 5,
            "megapixels_draft": 0.2,
            "audio_policy": "prefer_native",
            "allow_bulk": False,
        },
        "scenes": [{"id": "sc_combo", "shots": list(shots_by_id.values())}],
    }


def score_combo_row(row: dict[str, Any]) -> dict[str, float]:
    motion = float(row.get("motion_mean_absdiff") or row.get("motion_mean") or 0.0)
    ident = row.get("identity") if isinstance(row.get("identity"), dict) else {}
    start_l1 = ident.get("start_l1")
    mid_l1 = ident.get("mid_l1")
    end_l1 = ident.get("end_l1")
    mouth = float(row.get("mouth_region_std_change") or 0.0)
    if start_l1 is None:
        identity_score = 0.0
    else:
        s = float(start_l1)
        m = float(mid_l1) if mid_l1 is not None else s
        e = float(end_l1) if end_l1 is not None else m
        penalty = 0.5 * s + 0.3 * m + 0.2 * e
        identity_score = max(0.0, 100.0 - penalty)
    return {
        "identity_score": round(identity_score, 4),
        "motion_score": round(motion, 4),
        "mouth_score": round(mouth, 4),
        "hero_balanced": round(identity_score * 0.7 + min(motion, 40.0) * 0.3, 4),
    }


def rank_lanes(
    rows: list[dict[str, Any]],
    *,
    identity_start_max: float = 45.0,
) -> dict[str, Any]:
    enriched: list[dict[str, Any]] = []
    for r in rows:
        if not r.get("ok", True):
            continue
        enriched.append({**r, "scores": score_combo_row(r)})

    def _pick(cands: list[dict[str, Any]], key: Callable[[dict[str, Any]], float]) -> dict[str, Any] | None:
        if not cands:
            return None
        best = max(cands, key=key)
        return {
            "combo_id": best.get("combo_id"),
            "mode": best.get("mode"),
            "family": best.get("family"),
            "score": key(best),
            "scores": best.get("scores"),
            "motion_mean_absdiff": best.get("motion_mean_absdiff") or best.get("motion_mean"),
            "identity": best.get("identity"),
            "mouth_region_std_change": best.get("mouth_region_std_change"),
        }

    def _has_tag(r: dict[str, Any], tag: str) -> bool:
        tags = list(r.get("lane_tags") or [])
        fam_tags = {
            "soft_portrait": ["hero_identity_lock"],
            "high_motion": ["high_motion_energy", "hero_identity_lock"],
            "dialogue_mandarin": ["dialogue_mouth_energy", "hero_identity_lock"],
            "env_no_face": ["faceless_env"],
        }.get(str(r.get("family")), [])
        return tag in tags or tag in fam_tags

    id_cands = [
        r for r in enriched
        if r.get("mode") in {"i2v", "r2v", "flf"}
        and (_has_tag(r, "hero_identity_lock") or r.get("family") in {"soft_portrait", "high_motion", "dialogue_mandarin"})
        and isinstance(r.get("identity"), dict)
        and r["identity"].get("start_l1") is not None
    ]
    id_soft = [r for r in id_cands if r.get("family") == "soft_portrait"]
    hero = _pick(id_soft or id_cands, lambda r: float(r["scores"]["identity_score"]))

    hi_cands = [r for r in enriched if r.get("family") == "high_motion" or _has_tag(r, "high_motion_energy")]
    hi_locked = [
        r for r in hi_cands
        if not isinstance(r.get("identity"), dict)
        or r["identity"].get("start_l1") is None
        or float(r["identity"]["start_l1"]) <= identity_start_max
    ]
    high = _pick(hi_locked or hi_cands, lambda r: float(r["scores"]["motion_score"]))

    dlg_cands = [r for r in enriched if r.get("family") == "dialogue_mandarin" or _has_tag(r, "dialogue_mouth_energy")]
    dlg_locked = [
        r for r in dlg_cands
        if not isinstance(r.get("identity"), dict)
        or r["identity"].get("start_l1") is None
        or float(r["identity"]["start_l1"]) <= identity_start_max
    ]
    dialogue = _pick(
        dlg_locked or dlg_cands,
        lambda r: float(r["scores"]["mouth_score"]) * 2.0 + float(r["scores"]["identity_score"]) * 0.05,
    )

    env_cands = [
        r for r in enriched
        if r.get("mode") == "t2v" or r.get("family") == "env_no_face" or _has_tag(r, "faceless_env")
    ]
    env_true = [
        r for r in env_cands
        if not isinstance(r.get("identity"), dict)
        or r["identity"].get("start_l1") is None
        or r["identity"].get("note")
    ]
    if env_true and any((r.get("motion_mean_absdiff") or r.get("motion_mean")) is not None for r in env_true):
        faceless = _pick(env_true, lambda r: float(r["scores"]["motion_score"]))
    else:
        faceless = {
            "combo_id": "env_t2v_policy", "mode": "t2v", "family": "env_no_face",
            "score": None, "score_basis": "policy_only",
            "motion_mean_absdiff": None,
            "identity": {"start_l1": None, "note": "N/A policy_only"},
        }

    winners = {
        "hero_identity_lock": hero,
        "high_motion_energy": high,
        "dialogue_mouth_energy": dialogue,
        "faceless_env": faceless,
    }
    recipes: dict[str, Any] = {}
    for lane, w in winners.items():
        if not w:
            continue
        recipes[lane] = {
            "mode": w["mode"],
            "prompt_family": w["family"],
            "combo_id": w["combo_id"],
            "steps": DEFAULT_STEPS,
            "seed_policy": "fixed_for_ab_or_shot_seed",
            "score": w["score"],
        }
    return {
        "schema_version": 1,
        "kind": VERDICT_KIND,
        "ts": datetime.now(UTC).isoformat(),
        "winners": winners,
        "recipes": recipes,
        "rows_scored": len(enriched),
        "lanes_complete": [k for k, v in winners.items() if v is not None],
    }


def load_metrics_rows(path: Path | str) -> list[dict[str, Any]]:
    """Load ab-metrics.json rows (or a list JSON) for multi-round ranking."""
    p = Path(path).expanduser().resolve()
    if not p.is_file():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]
    if isinstance(data, dict):
        rows = data.get("rows")
        if isinstance(rows, list):
            return [r for r in rows if isinstance(r, dict)]
    return []


def rank_lanes_best_of(*row_groups: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
    """Rank across multiple rounds (R1+R2 rows)."""
    merged: list[dict[str, Any]] = []
    for group in row_groups:
        for r in group or []:
            if isinstance(r, dict):
                merged.append(dict(r))
    verdict = rank_lanes(merged, **kwargs)
    verdict["rounds_merged"] = len(row_groups)
    verdict["rows_input"] = len(merged)
    return verdict


def merge_winners_into_effect_defaults(verdict: dict[str, Any]) -> dict[str, Any]:

    recipes = verdict.get("recipes") if isinstance(verdict.get("recipes"), dict) else {}
    winners = verdict.get("winners") if isinstance(verdict.get("winners"), dict) else {}
    return {
        "schema_version": 1,
        "kind": "h3-combo-winners",
        "policy": "h3_max_effect_combo_v1",
        "source_verdict_kind": VERDICT_KIND,
        "ts": verdict.get("ts") or datetime.now(UTC).isoformat(),
        "lanes": {
            "hero_identity_lock": {
                "preferred_mode": (recipes.get("hero_identity_lock") or {}).get("mode", "i2v"),
                "prompt_family": (recipes.get("hero_identity_lock") or {}).get("prompt_family", "soft_portrait"),
                "notes": "Lock face from approved still; soft portrait control wins identity L1",
                "winner": winners.get("hero_identity_lock"),
            },
            "high_motion_energy": {
                "preferred_mode": (recipes.get("high_motion_energy") or {}).get("mode", "r2v"),
                "prompt_family": (recipes.get("high_motion_energy") or {}).get("prompt_family", "high_motion"),
                "notes": "HIGH MOTION clause required; R2V when energy > identity; I2V first if identity lock still required",
                "winner": winners.get("high_motion_energy"),
            },
            "dialogue_mouth_energy": {
                "preferred_mode": (recipes.get("dialogue_mouth_energy") or {}).get("mode", "i2v"),
                "prompt_family": (recipes.get("dialogue_mouth_energy") or {}).get("prompt_family", "dialogue_mandarin"),
                "notes": "Default I2V + Mandarin line inject; R2V only for extreme mouth CU when identity can float",
                "winner": winners.get("dialogue_mouth_energy"),
            },
            "faceless_env": {
                "preferred_mode": (recipes.get("faceless_env") or {}).get("mode", "t2v"),
                "prompt_family": (recipes.get("faceless_env") or {}).get("prompt_family", "env_no_face"),
                "notes": "Never hang cast face on T2V; env/bridge only",
                "winner": winners.get("faceless_env"),
            },
        },
        "weapon_defaults": {
            "steps": DEFAULT_STEPS,
            "duration_sec": 5.0,
            "fps": 24,
            "note": "registry tuning.steps.allowed is [20] only",
        },
    }


def probe_capacity(base_url: str | None = None) -> dict[str, Any]:
    from comfy_armory import default_base_url
    from comfy_video import submission_capacity

    return submission_capacity(base_url or default_base_url())


def wait_until_idle(
    *,
    base_url: str | None = None,
    poll_sec: float = 15.0,
    max_wait_sec: float = 3600.0,
    log: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    _log = log or (lambda _m: None)
    deadline = time.time() + max_wait_sec
    last: dict[str, Any] = {}
    while time.time() < deadline:
        last = probe_capacity(base_url)
        if last.get("ok") and str(last.get("status") or "") == "ready":
            _log("capacity ready")
            return last
        blockers = last.get("blockers") or []
        codes = [b.get("code") for b in blockers if isinstance(b, dict)]
        _log(f"capacity busy status={last.get('status')} blockers={codes}; sleep {poll_sec}s")
        time.sleep(poll_sec)
    last = last or probe_capacity(base_url)
    last["wait_timeout"] = True
    return last


def _ffmpeg_frame(video: Path, t_sec: float, out: Path) -> bool:
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-y", "-ss", f"{t_sec:.3f}", "-i", str(video), "-frames:v", "1", "-q:v", "2", str(out)]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=60)
        return proc.returncode == 0 and out.is_file()
    except (OSError, subprocess.TimeoutExpired):
        return False


def _l1_gray(path_a: Path, path_b: Path, size: tuple[int, int] = (140, 248)) -> float | None:
    w, h = size

    def _raw(p: Path) -> bytes | None:
        cmd = [
            "ffmpeg", "-y", "-i", str(p), "-vf", f"scale={w}:{h},format=gray",
            "-f", "rawvideo", "-pix_fmt", "gray", "pipe:1",
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, timeout=60)
        except (OSError, subprocess.TimeoutExpired):
            return None
        need = w * h
        if proc.returncode != 0 or len(proc.stdout) < need:
            return None
        return proc.stdout[:need]

    a, b = _raw(path_a), _raw(path_b)
    if not a or not b:
        return None
    return round(sum(abs(a[i] - b[i]) for i in range(len(a))) / float(len(a)), 4)


def _mouth_std_change(video: Path, work: Path) -> float | None:
    frames: list[Path] = []
    for i, t in enumerate((0.5, 1.5, 2.5, 3.5, 4.5)):
        fp = work / f"mouth_{i}.jpg"
        if _ffmpeg_frame(video, t, fp):
            frames.append(fp)
    if len(frames) < 2:
        return None
    w, h = 80, 48

    def _mouth_raw(p: Path) -> bytes | None:
        vf = f"scale=160:284,crop={w}:{h}:(160-{w})/2:284-{h}-20,format=gray"
        cmd = ["ffmpeg", "-y", "-i", str(p), "-vf", vf, "-f", "rawvideo", "-pix_fmt", "gray", "pipe:1"]
        try:
            proc = subprocess.run(cmd, capture_output=True, timeout=60)
        except (OSError, subprocess.TimeoutExpired):
            return None
        need = w * h
        if proc.returncode != 0 or len(proc.stdout) < need:
            return None
        return proc.stdout[:need]

    raws = [r for r in (_mouth_raw(f) for f in frames) if r]
    if len(raws) < 2:
        return None
    diffs: list[float] = []
    prev = raws[0]
    for cur in raws[1:]:
        diffs.append(sum(abs(cur[i] - prev[i]) for i in range(len(cur))) / float(len(cur)))
        prev = cur
    mean = sum(diffs) / len(diffs)
    var = sum((d - mean) ** 2 for d in diffs) / len(diffs)
    return round(mean + (var ** 0.5), 4)


def measure_clip_metrics(
    video: Path, *, still: Path | None, work_dir: Path, faceless: bool = False,
) -> dict[str, Any]:
    from i2v_motion_gate import measure_mean_absdiff

    work_dir.mkdir(parents=True, exist_ok=True)
    mean = measure_mean_absdiff(video)
    dur = 5.0
    try:
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(video)],
            capture_output=True, text=True, timeout=30,
        )
        if probe.returncode == 0 and probe.stdout.strip():
            dur = max(0.5, float(probe.stdout.strip()))
    except (OSError, subprocess.TimeoutExpired, ValueError):
        pass
    t_start, t_mid, t_end = 0.05, dur * 0.5, max(0.1, dur - 0.15)
    start_f, mid_f, end_f = work_dir / "start.jpg", work_dir / "mid.jpg", work_dir / "end.jpg"
    _ffmpeg_frame(video, t_start, start_f)
    _ffmpeg_frame(video, t_mid, mid_f)
    _ffmpeg_frame(video, t_end, end_f)
    if faceless or still is None or not still.is_file():
        identity: dict[str, Any] = {
            "start_l1": None, "mid_l1": None, "end_l1": None, "note": "N/A faceless or no still",
        }
    else:
        identity = {
            "start_l1": _l1_gray(still, start_f) if start_f.is_file() else None,
            "mid_l1": _l1_gray(still, mid_f) if mid_f.is_file() else None,
            "end_l1": _l1_gray(still, end_f) if end_f.is_file() else None,
        }
    mouth = _mouth_std_change(video, work_dir / "mouth") if not faceless else None
    return {
        "motion_mean_absdiff": mean,
        "motion_mean": mean,
        "identity": identity,
        "mouth_region_std_change": mouth,
        "size_bytes": video.stat().st_size if video.is_file() else 0,
        "duration_sec": dur,
        "frames": {
            "start": str(start_f) if start_f.is_file() else None,
            "mid": str(mid_f) if mid_f.is_file() else None,
            "end": str(end_f) if end_f.is_file() else None,
        },
    }


def prepare_eval_root(
    eval_root: Path | str,
    *,
    source_still: Path | str | None = None,
    end_still: Path | str | None = None,
    combos: list[ComboSpec] | None = None,
) -> Path:
    root = Path(eval_root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    combos = combos or build_combo_matrix()
    (root / "film-spec.json").write_text(
        json.dumps(build_eval_film_spec(combos), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    stills = root / "stills"
    stills.mkdir(exist_ok=True)
    prompts = root / "receipts" / "prompts"
    prompts.mkdir(parents=True, exist_ok=True)
    for d in ("takes", "receipts", "compare"):
        (root / d).mkdir(exist_ok=True)
    src = Path(source_still).expanduser().resolve() if source_still else None
    end = Path(end_still).expanduser().resolve() if end_still else None
    seen: set[str] = set()
    for c in combos:
        if c.shot_id in seen:
            continue
        seen.add(c.shot_id)
        text = compile_family_author_prompt(
            c.family, shot_id=c.shot_id, duration_sec=5.0, mode=c.mode
        )
        (prompts / f"{c.shot_id}.i2v.txt").write_text(text + "\n", encoding="utf-8")
        if c.mode != "t2v" and c.family != "env_no_face":
            dest = stills / f"{c.shot_id}.png"
            if src and src.is_file() and not dest.is_file():
                shutil.copy2(src, dest)
            if c.requires_last or c.mode == "flf":
                end_dest = stills / f"{c.shot_id}_end.png"
                if end and end.is_file() and not end_dest.is_file():
                    shutil.copy2(end, end_dest)
    (root / "compare" / "combo-matrix.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "kind": "h3-combo-matrix",
                "seed": DEFAULT_SEED,
                "steps": DEFAULT_STEPS,
                "combos": [c.to_dict() for c in combos],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return root


def run_combo_grid(
    eval_root: Path | str,
    *,
    combos: list[ComboSpec] | None = None,
    base_url: str | None = None,
    poll_sec: float = 20.0,
    max_wait_per_job_sec: float = 3600.0,
    free_memory_on_mode_switch: bool = True,
    execute: bool = True,
    scratch_dir: Path | str | None = None,
    log: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    from util import write_json

    root = Path(eval_root).expanduser().resolve()
    combos = combos or build_combo_matrix()
    _log = log or (lambda m: print(m, flush=True))
    scratch = Path(scratch_dir).expanduser().resolve() if scratch_dir else None
    if scratch:
        (scratch / "combo-runs").mkdir(parents=True, exist_ok=True)
    compare = root / "compare"
    compare.mkdir(exist_ok=True)
    rows: list[dict[str, Any]] = []
    last_mode: str | None = None
    capacity_log: list[dict[str, Any]] = []

    if not execute:
        plan = {"ok": True, "dry_run": True, "combos": [c.to_dict() for c in combos], "eval_root": str(root)}
        write_json(compare / "dry-plan.json", plan)
        return plan

    for c in combos:
        if c.requires_last or c.mode == "flf":
            if not (root / "stills" / f"{c.shot_id}_end.png").is_file():
                row = {
                    "ok": False, "combo_id": c.combo_id, "mode": c.mode, "family": c.family,
                    "shot_id": c.shot_id, "lane_tags": c.lane_tags, "skipped": True, "skip_reason": "no_end_still",
                }
                rows.append(row)
                write_json(compare / f"{c.combo_id}.json", row)
                _log(f"skip {c.combo_id}: no end still")
                continue

        _log(f"wait capacity for {c.combo_id} ({c.mode}/{c.family})…")
        cap = wait_until_idle(base_url=base_url, poll_sec=poll_sec, max_wait_sec=max_wait_per_job_sec, log=_log)
        capacity_log.append({
            "combo_id": c.combo_id,
            "capacity": {"status": cap.get("status"), "blockers": cap.get("blockers"), "ok": cap.get("ok"), "wait_timeout": cap.get("wait_timeout")},
        })
        if not (cap.get("ok") and str(cap.get("status")) == "ready"):
            row = {
                "ok": False, "combo_id": c.combo_id, "mode": c.mode, "family": c.family,
                "shot_id": c.shot_id, "lane_tags": c.lane_tags, "error": "capacity_timeout_or_blocked",
                "capacity": capacity_log[-1]["capacity"],
            }
            rows.append(row)
            write_json(compare / f"{c.combo_id}.json", row)
            continue

        # Free after every prior job (not only mode switch): residual VRAM often
        # stays below 24GiB floor even when queue is idle (R5 2026-08-06).
        if free_memory_on_mode_switch and last_mode is not None:
            try:
                from comfy_armory import default_base_url
                from comfy_video import free_memory
                reason = (
                    f"mode switch {last_mode}→{c.mode}"
                    if last_mode != c.mode
                    else f"post-job free after {last_mode}"
                )
                _log(f"free-memory ({reason})")
                free_memory(base_url or default_base_url())
                time.sleep(3)
            except Exception as exc:  # noqa: BLE001
                _log(f"free-memory warning: {exc}")

        prompt_text = ""
        pfile = root / "receipts" / "prompts" / f"{c.shot_id}.i2v.txt"
        if pfile.is_file():
            prompt_text = pfile.read_text(encoding="utf-8").strip()
        still_path = root / "stills" / f"{c.shot_id}.png"
        still_for_run = still_path if still_path.is_file() else None
        last_path = root / "stills" / f"{c.shot_id}_end.png"
        last_for_run = last_path if last_path.is_file() else None

        _log(f"run {c.combo_id}: mode={c.mode} seed={c.seed}")
        try:
            from h3_workflow import run_h3_shot
            run_receipt = run_h3_shot(
                root, c.shot_id, mode=c.mode, register=False, seed=c.seed,
                timeout_sec=1800, enqueue_queue=False, production_stage="pilot",
                allow_experimental=True, still_override=still_for_run,
                last_override=last_for_run if c.mode == "flf" else None,
            )
        except Exception as exc:  # noqa: BLE001
            row = {
                "ok": False, "combo_id": c.combo_id, "mode": c.mode, "family": c.family,
                "shot_id": c.shot_id, "lane_tags": c.lane_tags, "seed": c.seed,
                "steps": c.steps if isinstance(c.steps, int) else "weapon_default",
                "prompt_text": prompt_text, "still_path": str(still_for_run) if still_for_run else None,
                "error": str(exc),
            }
            rows.append(row)
            write_json(compare / f"{c.combo_id}.json", row)
            if scratch:
                write_json(scratch / "combo-runs" / f"{c.combo_id}.json", row)
            last_mode = c.mode
            continue

        deliver = Path(str(run_receipt.get("deliver_path") or run_receipt.get("raw_path") or ""))
        faceless = c.mode == "t2v" or c.family == "env_no_face"
        metrics = (
            measure_clip_metrics(
                deliver, still=still_for_run if not faceless else None,
                work_dir=compare / f"_frames_{c.combo_id}", faceless=faceless,
            )
            if deliver.is_file()
            else {"error": "no_deliver_path", "motion_mean_absdiff": None}
        )
        spine = root / "receipts" / "prompts" / f"{c.shot_id}.h3.spine.txt"
        if spine.is_file():
            prompt_text = spine.read_text(encoding="utf-8").strip() or prompt_text
        row = {
            "ok": bool(run_receipt.get("ok", True)) and deliver.is_file(),
            "combo_id": c.combo_id, "mode": c.mode, "family": c.family, "shot_id": c.shot_id,
            "lane_tags": c.lane_tags, "seed": c.seed,
            "steps": c.steps if isinstance(c.steps, int) else "weapon_default",
            "prompt_text": prompt_text,
            "still_path": str(still_for_run) if still_for_run else None,
            "last_path": str(last_for_run) if last_for_run else None,
            "deliver_path": str(deliver) if deliver.is_file() else None,
            "run_receipt": {k: run_receipt.get(k) for k in ("ok", "weapon_id", "source_endpoint", "raw_path", "deliver_path", "receipt")},
            "motion_mean_absdiff": metrics.get("motion_mean_absdiff"),
            "motion_mean": metrics.get("motion_mean"),
            "identity": metrics.get("identity"),
            "mouth_region_std_change": metrics.get("mouth_region_std_change"),
            "size_bytes": metrics.get("size_bytes"),
            "duration_sec": metrics.get("duration_sec"),
            "frame_extracts": metrics.get("frames"),
        }
        rows.append(row)
        write_json(compare / f"{c.combo_id}.json", row)
        if scratch:
            write_json(scratch / "combo-runs" / f"{c.combo_id}.json", row)
        _log(f"done {c.combo_id}: motion={row.get('motion_mean_absdiff')} id_start={(row.get('identity') or {}).get('start_l1')}")
        last_mode = c.mode

    ab_metrics = {
        "schema_version": 1, "kind": "h3-combo-ab-metrics",
        "ts": datetime.now(UTC).isoformat(),
        "seed": DEFAULT_SEED, "steps": DEFAULT_STEPS, "eval_root": str(root),
        "rows": rows, "capacity_log_tail": capacity_log[-5:],
    }
    write_json(compare / "ab-metrics.json", ab_metrics)
    verdict = rank_lanes(rows)
    write_json(compare / "verdict.json", verdict)
    winners_doc = merge_winners_into_effect_defaults(verdict)
    write_json(compare / "winners-merged.json", winners_doc)
    if scratch:
        write_json(scratch / "h3-combo-verdict.json", verdict)
        write_json(scratch / "ab-metrics.json", ab_metrics)
        write_json(scratch / "capacity-log.json", capacity_log)
    return {
        "ok": any(r.get("ok") for r in rows),
        "eval_root": str(root),
        "rows": rows,
        "verdict": verdict,
        "winners": winners_doc,
        "capacity_events": len(capacity_log),
        "lanes_complete": verdict.get("lanes_complete") or [],
    }


def load_combo_winners(path: Path | str | None = None) -> dict[str, Any] | None:
    if path is None:
        here = Path(__file__).resolve().parent.parent
        candidates = [here.parent / "registry" / "h3-combo-winners.json", here / "h3-combo-winners.json"]
    else:
        candidates = [Path(path).expanduser().resolve()]
    for p in candidates:
        if p.is_file():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(data, dict):
                return data
    return None


def winner_tips_from_registry(winners: dict[str, Any] | None = None) -> list[str]:
    data = winners if winners is not None else load_combo_winners()
    if not data:
        return []
    lanes = data.get("lanes") if isinstance(data.get("lanes"), dict) else {}
    tips: list[str] = []
    labels = {
        "hero_identity_lock": "身份锁脸",
        "high_motion_energy": "高动能量",
        "dialogue_mouth_energy": "对白嘴型",
        "faceless_env": "无脸环境",
    }
    for key in ("hero_identity_lock", "high_motion_energy", "dialogue_mouth_energy", "faceless_env"):
        lane = lanes.get(key) if isinstance(lanes.get(key), dict) else None
        if not lane:
            continue
        w = lane.get("winner") if isinstance(lane.get("winner"), dict) else {}
        score = w.get("score")
        score_s = f" score={score}" if score is not None else ""
        tips.append(
            f"combo-win {labels.get(key, key)}: mode={lane.get('preferred_mode') or '?'} "
            f"family={lane.get('prompt_family') or '?'}{score_s}"
        )
    if data.get("weapon_defaults"):
        wd = data["weapon_defaults"]
        tips.append(
            f"combo weapon defaults: steps={wd.get('steps')} duration={wd.get('duration_sec')}s (registry-locked)"
        )
    return tips


def write_winners_registry(winners_doc: dict[str, Any], *, path: Path | str | None = None) -> Path:
    if path is None:
        path = Path(__file__).resolve().parents[2] / "registry" / "h3-combo-winners.json"
    p = Path(path).expanduser().resolve()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(winners_doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return p

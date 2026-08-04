#!/usr/bin/env python3
"""MiniMax H3 mode selection — max-effect policy (I2V / R2V / T2V).

5090-proven rules (2026-08-04):
  I2V  — lock face from approved still (hero / meat / continue / reaction)
  R2V  — energy, big-mouth CU dialogue, hard pose when I2V is soft
  T2V  — faceless env/bridge only (never hang a character face)

Single source for ``h3 plan`` / ``h3 list`` / agent routing.
"""

from __future__ import annotations

from typing import Any

H3_MODE_WEAPON = {
    "t2v": "minimax-h3-t2v-pilot",
    "i2v": "minimax-h3-i2v-pilot",
    "r2v": "minimax-h3-r2v-pilot",
}
H3_MODE_ENDPOINT = {
    "t2v": "local_minimax_h3_t2v",
    "i2v": "local_minimax_h3_i2v",
    "r2v": "local_minimax_h3_r2v",
}

_CLOSE_SIZES = frozenset(
    {
        "cu",
        "ecu",
        "close",
        "closeup",
        "close_up",
        "close-up",
        "extreme_close",
        "extreme_closeup",
        "extreme_close_up",
        "l4",
        "insert_l4",
        "mcu",
        "medium_close",
        "medium_closeup",
    }
)
_R2V_ENERGY_FLAGS = (
    "deep_thrust",
    "creampie",
    "internal_peak",
    "penetration",
    "l4_contact",
    "long_meat",
    "sex_pose",
)
_RESTRICTED_HEAT = frozenset({"foreplay", "act", "climax", "afterglow"})
_BARE_WARDROBE = frozenset({"partial", "undressed", "bare"})


def shot_size_token(shot: dict[str, Any]) -> str:
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    camera = dsl.get("camera") if isinstance(dsl.get("camera"), dict) else {}
    raw = (
        shot.get("shot_size")
        or dsl.get("shot_size")
        or camera.get("shot_size")
        or shot.get("framing")
        or ""
    )
    return str(raw).strip().lower().replace(" ", "_")


def spoken_text_of(shot: dict[str, Any], intent: dict[str, Any] | None = None) -> str:
    if isinstance(intent, dict):
        t = str(intent.get("spoken_text") or "").strip()
        if t:
            return t
    try:
        from motion_prompt_spine import spoken_dialogue_text

        t = spoken_dialogue_text(shot)
        if t:
            return t
    except Exception:
        pass
    cues = shot.get("audio_cues") if isinstance(shot.get("audio_cues"), list) else []
    for cue in cues:
        if isinstance(cue, dict):
            line = str(cue.get("spoken_text") or cue.get("text") or "").strip()
            if line:
                return line
    return str(shot.get("spoken_text") or shot.get("dialogue") or "").strip()


def screen_mode_of(shot: dict[str, Any], intent: dict[str, Any] | None = None) -> str:
    if isinstance(intent, dict):
        s = str(intent.get("screen_mode") or "").strip().lower()
        if s:
            return s
    s = str(shot.get("screen_mode") or "").strip().lower()
    if s:
        return s
    cues = shot.get("audio_cues") if isinstance(shot.get("audio_cues"), list) else []
    for cue in cues:
        if isinstance(cue, dict) and str(cue.get("spoken_text") or "").strip():
            return str(cue.get("screen_mode") or "on_camera").strip().lower()
    return ""


def wants_continue_shot(shot: dict[str, Any]) -> bool:
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    chain = str(dsl.get("chain_mode") or shot.get("chain_mode") or "").strip().lower()
    if chain == "continue":
        return True
    return bool(str(shot.get("parent_shot_id") or "").strip())


def explicit_h3_mode(shot: dict[str, Any], intent: dict[str, Any] | None = None) -> str | None:
    for key in ("h3_mode", "motion_mode"):
        raw = str(shot.get(key) or "").strip().lower()
        if raw in {"t2v", "i2v", "r2v"}:
            return raw
    op = str(shot.get("operation") or "").strip().lower().replace("-", "_")
    if op in {"reference_to_video", "r2v"}:
        return "r2v"
    if op in {"text_to_video", "t2v"}:
        return "t2v"
    if op in {"image_to_video", "i2v"}:
        return "i2v"
    if isinstance(intent, dict):
        iop = str(intent.get("operation") or "").strip().lower().replace("-", "_")
        if iop == "reference_to_video":
            return "r2v"
    return None


def _pack(
    mode: str,
    *,
    reasons: list[str],
    alt_mode: str | None = None,
    alt_reasons: list[str] | None = None,
    confidence: str = "hard",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "schema_version": 1,
        "kind": "ai-film-h3-mode-resolve",
        "mode": mode,
        "weapon_id": H3_MODE_WEAPON[mode],
        "source_endpoint": H3_MODE_ENDPOINT[mode],
        "requires_still": mode in {"i2v", "r2v"},
        "reasons": reasons,
        "alt_mode": alt_mode,
        "alt_reasons": list(alt_reasons or []),
        "policy": "h3_max_effect_v1",
        "confidence": confidence,
    }
    if extra:
        out.update(extra)
    return out


def resolve_h3_mode(
    shot: dict[str, Any],
    *,
    intent: dict[str, Any] | None = None,
    has_still: bool | None = None,
    wants_continue: bool | None = None,
) -> dict[str, Any]:
    """Pick H3 mode for max effect (identity first, energy second)."""
    sh = shot if isinstance(shot, dict) else {}
    intent = intent if isinstance(intent, dict) else {}
    role = str(intent.get("shot_role") or sh.get("shot_role") or "hero").strip().lower()
    heat = str(intent.get("heat_phase") or sh.get("heat_phase") or "").strip().lower()
    wardrobe = str(intent.get("wardrobe_state") or sh.get("wardrobe_state") or "").strip().lower()
    flags = [str(f) for f in (intent.get("difficulty_flags") or [])]
    flag_blob = " ".join(flags).lower()
    restricted = bool(
        intent.get("content_class") == "restricted_local"
        or flags
        or (heat in _RESTRICTED_HEAT and wardrobe in _BARE_WARDROBE)
        or heat in {"act", "climax"}
    )
    if wants_continue is None:
        wants_continue = wants_continue_shot(sh)
    if has_still is None:
        has_still = False

    spoken = spoken_text_of(sh, intent)
    screen = screen_mode_of(sh, intent)
    size = shot_size_token(sh)
    motion_tier = str(intent.get("motion_tier") or "").strip().lower()
    if not motion_tier:
        try:
            from motion_prompt_spine import motion_tier_for

            motion_tier = motion_tier_for(sh)
        except Exception:
            motion_tier = "medium"

    explicit = explicit_h3_mode(sh, intent)
    if explicit:
        return _pack(explicit, reasons=[f"explicit:{explicit}"], confidence="hard")

    if wants_continue:
        return _pack("i2v", reasons=["continue_endframe_lock"], confidence="hard")

    if role in {"env", "bridge"}:
        return _pack("t2v", reasons=["faceless_env_t2v"], confidence="hard")

    if str(intent.get("operation") or "") == "text_to_video" and role != "hero":
        return _pack("t2v", reasons=["operation_text_to_video"], confidence="hard")

    if role == "insert":
        if has_still:
            return _pack(
                "i2v",
                reasons=["insert_detail_still"],
                alt_mode="r2v",
                alt_reasons=["retry_energy_if_static"],
                confidence="medium",
            )
        return _pack("t2v", reasons=["insert_no_still_t2v"], confidence="medium")

    energy_hits: list[str] = []
    on_cam = bool(spoken) and screen in {"on_camera", "on-camera", ""}
    close = size in _CLOSE_SIZES or size.endswith("_cu") or "close" in size
    if restricted and on_cam and close:
        energy_hits.append("dialogue_close_r2v")
    if restricted and motion_tier == "high":
        if any(tok in flag_blob for tok in _R2V_ENERGY_FLAGS):
            energy_hits.append("high_motion_difficulty")
        if heat in {"act", "climax"} and any(
            tok in flag_blob for tok in ("sex_pose", "deep_thrust", "penetration", "l4_contact")
        ):
            energy_hits.append("meat_pose_energy")
    if sh.get("force_r2v") is True or str(sh.get("h3_prefer") or "").lower() == "r2v":
        energy_hits.append("force_r2v")

    if energy_hits and has_still:
        return _pack(
            "r2v",
            reasons=[*energy_hits, "r2v_energy_lane"],
            alt_mode="i2v",
            alt_reasons=["fallback_identity_lock"],
            confidence="medium",
            extra={"motion_tier": motion_tier, "shot_size": size or None, "restricted": True},
        )

    alt_mode: str | None = None
    alt_reasons: list[str] = []
    if restricted and motion_tier == "high" and has_still:
        alt_mode = "r2v"
        alt_reasons = ["retry_if_motion_mean_low", "high_motion_tier"]
    if restricted and on_cam and spoken and has_still and not close:
        alt_mode = alt_mode or "r2v"
        if "retry_if_lip_weak" not in alt_reasons:
            alt_reasons.append("retry_if_lip_weak")

    reasons = ["identity_still_i2v" if has_still else "hero_planned_i2v_needs_still"]
    if restricted:
        reasons.append("restricted_hero")
    if spoken:
        reasons.append("dialogue_inject")

    return _pack(
        "i2v",
        reasons=reasons,
        alt_mode=alt_mode,
        alt_reasons=alt_reasons,
        confidence="medium" if alt_mode else "hard",
        extra={
            "motion_tier": motion_tier,
            "shot_size": size or None,
            "restricted": bool(restricted),
        },
    )


def effect_tips(mode: str, mode_res: dict[str, Any] | None = None) -> list[str]:
    mode_res = mode_res or {}
    tips = [
        "换模式前: aifilm comfy free-memory --confirm",
        "产能: aifilm comfy capacity（free VRAM≥24GiB · queue idle）",
    ]
    if mode == "i2v":
        tips.append("I2V 锁脸：源 still 须已是目标体位/状态；软肖像 prompt 会静")
        tips.append("高动写清 HIGH MOTION + 每秒可见变化；不够再 --mode r2v")
        if mode_res.get("alt_mode") == "r2v":
            tips.append(f"能量备胎 R2V：{mode_res.get('alt_reasons')}")
    elif mode == "r2v":
        tips.append("R2V 参考演：身份弱于 I2V；要像素贴 still 请改 --mode i2v")
        tips.append("适合大嘴 CU / 邻镜换构图 / 体位高动")
    elif mode == "t2v":
        tips.append("T2V 禁挂角色脸；只做无脸 env/bridge/气氛")
    tips.append("对白：audio_cues.spoken_text + on_camera → 自动注入 line:「…」")
    tips.append("续镜：dsl.chain_mode=continue → 自动末帧 I2V handoff")
    return tips

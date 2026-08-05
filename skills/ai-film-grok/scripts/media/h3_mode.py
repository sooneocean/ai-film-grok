#!/usr/bin/env python3
"""MiniMax H3 mode selection — max-effect policy (I2V / FLF / R2V / T2V).

5090-proven rules (2026-08-04 + FLF):
  I2V  — lock face from approved still (hero / meat / continue / reaction)
  FLF  — first+last frame on same fl2va I2V weapon (pose A→B land)
  R2V  — energy, big-mouth CU dialogue, hard pose when I2V is soft
  T2V  — faceless env/bridge only (never hang a character face)

Single source for ``h3 plan`` / ``h3 list`` / agent routing.
"""

from __future__ import annotations

from typing import Any

H3_MODE_WEAPON = {
    "t2v": "minimax-h3-t2v-pilot",
    "i2v": "minimax-h3-i2v-pilot",
    "flf": "minimax-h3-i2v-pilot",
    "r2v": "minimax-h3-r2v-pilot",
}
H3_MODE_ENDPOINT = {
    "t2v": "local_minimax_h3_t2v",
    "i2v": "local_minimax_h3_i2v",
    "flf": "local_minimax_h3_i2v",
    "r2v": "local_minimax_h3_r2v",
}
_VALID_MODES = frozenset({"t2v", "i2v", "flf", "r2v"})

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
        if raw in _VALID_MODES:
            return raw
        if raw in {"first_last", "first_last_frame", "i2v_flf", "fl2v", "fl2va"}:
            return "flf"
    op = str(shot.get("operation") or "").strip().lower().replace("-", "_")
    if op in {"reference_to_video", "r2v"}:
        return "r2v"
    if op in {"text_to_video", "t2v"}:
        return "t2v"
    if op in {"first_last_frame", "first_last_frame_i2v", "flf"}:
        return "flf"
    if op in {"image_to_video", "i2v"}:
        return "i2v"
    if isinstance(intent, dict):
        iop = str(intent.get("operation") or "").strip().lower().replace("-", "_")
        if iop == "reference_to_video":
            return "r2v"
        if iop in {"first_last_frame", "first_last_frame_i2v"}:
            return "flf"
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
        "requires_still": mode in {"i2v", "flf", "r2v"},
        "requires_last": mode == "flf",
        "reasons": reasons,
        "alt_mode": alt_mode,
        "alt_reasons": list(alt_reasons or []),
        "policy": "h3_max_effect_v2_first_last",
        "confidence": confidence,
    }
    if extra:
        out.update(extra)
    return out


def resolve_h3_mode_core(
    shot: dict[str, Any],
    *,
    intent: dict[str, Any] | None = None,
    has_still: bool | None = None,
    has_last: bool | None = None,
    wants_continue: bool | None = None,
) -> dict[str, Any]:
    """Pick H3 mode for max effect (identity first, land-point FLF, energy second)."""
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
    if has_last is None:
        has_last = False
    force_single = sh.get("force_i2v_single") is True or str(sh.get("h3_prefer") or "").lower() in {
        "i2v",
        "single",
        "i2v_single",
    }

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
        if explicit == "flf" and not has_last:
            return _pack(
                "i2v",
                reasons=["explicit:flf", "last_missing_fallback_i2v"],
                confidence="medium",
            )
        return _pack(explicit, reasons=[f"explicit:{explicit}"], confidence="hard")

    if wants_continue:
        if has_last and has_still and not force_single:
            return _pack(
                "flf",
                reasons=["continue_endframe_lock", "last_frame_land"],
                alt_mode="i2v",
                alt_reasons=["single_frame_if_last_poison"],
                confidence="hard",
            )
        return _pack("i2v", reasons=["continue_endframe_lock"], confidence="hard")

    if role in {"env", "bridge"}:
        return _pack("t2v", reasons=["faceless_env_t2v"], confidence="hard")

    if str(intent.get("operation") or "") == "text_to_video" and role != "hero":
        return _pack("t2v", reasons=["operation_text_to_video"], confidence="hard")

    if role == "insert":
        if has_still and has_last and not force_single:
            return _pack(
                "flf",
                reasons=["insert_first_last_land"],
                alt_mode="i2v",
                alt_reasons=["insert_detail_still"],
                confidence="medium",
            )
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
    # Combo winners: dialogue_mouth_energy prefers I2V; skip R2V force when registry says i2v.
    dlg_combo_pref = preferred_mode_for_lane("dialogue_mouth_energy")
    if restricted and on_cam and close and dlg_combo_pref != "i2v":
        energy_hits.append("dialogue_close_r2v")
    if restricted and motion_tier == "high":
        if any(tok in flag_blob for tok in _R2V_ENERGY_FLAGS):
            energy_hits.append("high_motion_difficulty")
        if heat in {"act", "climax"} and any(
            tok in flag_blob for tok in ("sex_pose", "deep_thrust", "penetration", "l4_contact")
        ):
            energy_hits.append("meat_pose_energy")
    force_r2v = sh.get("force_r2v") is True or str(sh.get("h3_prefer") or "").lower() == "r2v"
    if force_r2v:
        energy_hits.append("force_r2v")

    # force_r2v always energy lane (last still becomes pose ref in workflow, not FLF).
    if force_r2v and has_still:
        alt = "flf" if has_last and not force_single else "i2v"
        alt_rs = ["fallback_flf_land"] if alt == "flf" else ["fallback_identity_lock"]
        return _pack(
            "r2v",
            reasons=[*energy_hits, "r2v_energy_lane"],
            alt_mode=alt,
            alt_reasons=alt_rs,
            confidence="medium",
            extra={
                "motion_tier": motion_tier,
                "shot_size": size or None,
                "restricted": True,
                "uses_last_as_pose_ref": bool(has_last),
            },
        )

    # First+last present → FLF primary (quality land). Energy is alt, not primary.
    if has_still and has_last and not force_single:
        alt_mode: str | None = None
        alt_reasons: list[str] = []
        if energy_hits or (restricted and motion_tier == "high"):
            alt_mode = "r2v"
            alt_reasons = (
                list(energy_hits)
                if energy_hits
                else [
                    "retry_if_motion_mean_low",
                    "high_motion_tier",
                ]
            )
            if "r2v_energy_lane" not in alt_reasons:
                alt_reasons.append("r2v_energy_lane")
        return _pack(
            "flf",
            reasons=["identity_still_flf", "last_frame_present", "first_last_primary"],
            alt_mode=alt_mode,
            alt_reasons=alt_reasons,
            confidence="medium" if alt_mode else "hard",
            extra={
                "motion_tier": motion_tier,
                "shot_size": size or None,
                "restricted": bool(restricted),
            },
        )

    # No last frame: energy flags may still pick R2V (single-still / multi-ref path).
    if energy_hits and has_still:
        return _pack(
            "r2v",
            reasons=[*energy_hits, "r2v_energy_lane"],
            alt_mode="i2v",
            alt_reasons=["fallback_identity_lock", "produce_end_still_for_flf"],
            confidence="medium",
            extra={"motion_tier": motion_tier, "shot_size": size or None, "restricted": True},
        )

    alt_mode = None
    alt_reasons = []
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
    if (
        restricted
        and on_cam
        and close
        and spoken
        and has_still
        and dlg_combo_pref == "i2v"
        and not force_r2v
    ):
        reasons.append("combo_win_dialogue_i2v")
        alt_mode = "r2v"
        if "combo_alt_r2v_mouth_cu" not in (alt_reasons or []):
            alt_reasons = list(alt_reasons or []) + ["combo_alt_r2v_mouth_cu"]

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
    try:
        from h3_combo_eval import winner_tips_from_registry

        tips.extend(winner_tips_from_registry())
    except Exception:
        pass
    if mode == "i2v":
        tips.append("I2V 单首帧：源 still 须已是目标体位/状态；软肖像 prompt 会静")
        tips.append("质量优先：补 stills/<id>_end.png 后自动升 FLF（first+last）")
        tips.append("高动写清 HIGH MOTION + 每秒可见变化；不够再 --mode r2v")
        tips.append("combo lane: 身份锁脸默认 I2V+soft_portrait；高动先 I2V+HIGH MOTION 再 R2V")
        tips.append("R2: soft_portrait_alive 防静帧；high_motion_max 每0.5s大姿变；dialogue_mouth_max 下颌开合")
        if mode_res.get("alt_mode") == "r2v":
            tips.append(f"能量备胎 R2V：{mode_res.get('alt_reasons')}")
    elif mode == "flf":
        tips.append("FLF 首尾帧：first=开场 still，last=收场姿势；fl2va last_frame 硬接")
        tips.append("禁 first 复制成 last；last 须过身份/毒镜门")
        tips.append("落点不对 → 重做 end still；要自由高动 → --mode r2v（last 作 pose ref）")
        if mode_res.get("alt_mode") == "r2v":
            tips.append(f"能量备胎 R2V：{mode_res.get('alt_reasons')}")
    elif mode == "r2v":
        tips.append("R2V：first=主 ref0；有 end still 时 last 优先作 pose land ref")
        tips.append("身份弱于 I2V/FLF；要像素贴落点 → --mode flf + --last-frame")
        tips.append("适合大嘴 CU / 邻镜换构图 / force_r2v 体位高动")
        tips.append("combo lane: 高动能量位优先 R2V+high_motion family")
    elif mode == "t2v":
        tips.append("T2V 禁挂角色脸；只做无脸 env/bridge/气氛")
        tips.append("combo lane: faceless_env → T2V+env_no_face only")
    tips.append("对白：audio_cues.spoken_text + on_camera → 自动注入 line:「…」")
    tips.append("combo lane: 对白默认 I2V+dialogue_mandarin；极端大嘴 CU 才 R2V")
    tips.append("续镜：dsl.chain_mode=continue → 自动末帧作 first；有 last 则 FLF")
    return tips


def preferred_mode_for_lane(lane: str) -> str | None:
    """Return combo-eval preferred mode for a production lane (if registry present)."""
    try:
        from h3_combo_eval import load_combo_winners

        data = load_combo_winners()
    except Exception:
        return None
    if not data:
        return None
    lanes = data.get("lanes") if isinstance(data.get("lanes"), dict) else {}
    entry = lanes.get(lane) if isinstance(lanes.get(lane), dict) else None
    if not entry:
        return None
    mode = entry.get("preferred_mode")
    return str(mode) if mode else None


def infer_combo_lane(
    shot: dict[str, Any],
    *,
    intent: dict[str, Any] | None = None,
    has_still: bool = False,
) -> str | None:
    """Map a shot to a combo-eval lane (for registry preferred_mode)."""
    sh = shot if isinstance(shot, dict) else {}
    intent = intent if isinstance(intent, dict) else {}
    role = str(intent.get("shot_role") or sh.get("shot_role") or "hero").strip().lower()
    if role in {"env", "bridge"}:
        return "faceless_env"
    spoken = spoken_text_of(sh, intent)
    screen = screen_mode_of(sh, intent)
    size = shot_size_token(sh)
    close = size in _CLOSE_SIZES or size.endswith("_cu") or "close" in size
    on_cam = bool(spoken) and screen in {"on_camera", "on-camera", ""}
    motion_tier = str(intent.get("motion_tier") or "").strip().lower()
    if not motion_tier:
        try:
            from motion_prompt_spine import motion_tier_for

            motion_tier = motion_tier_for(sh)
        except Exception:
            motion_tier = "medium"
    heat = str(intent.get("heat_phase") or sh.get("heat_phase") or "").strip().lower()
    flags = [str(f) for f in (intent.get("difficulty_flags") or [])]
    flag_blob = " ".join(flags).lower()
    if spoken and on_cam and close:
        return "dialogue_mouth_energy"
    if motion_tier == "high" or any(tok in flag_blob for tok in _R2V_ENERGY_FLAGS):
        return "high_motion_energy"
    if heat in {"act", "climax"} and any(
        tok in flag_blob for tok in ("sex_pose", "deep_thrust", "penetration", "l4_contact")
    ):
        return "high_motion_energy"
    if has_still or role in {"hero", "insert"}:
        return "hero_identity_lock"
    return None


def annotate_combo_resolve(
    pack: dict[str, Any],
    *,
    lane: str | None,
) -> dict[str, Any]:
    """Attach combo-eval preferred mode/family onto a resolve pack (live plan path)."""
    if not isinstance(pack, dict):
        return pack
    if not lane:
        return pack
    preferred = preferred_mode_for_lane(lane)
    family = None
    try:
        from h3_combo_eval import load_combo_winners

        data = load_combo_winners() or {}
        lanes = data.get("lanes") if isinstance(data.get("lanes"), dict) else {}
        entry = lanes.get(lane) if isinstance(lanes.get(lane), dict) else {}
        family = (entry or {}).get("prompt_family")
    except Exception:
        pass
    pack = dict(pack)
    pack["combo_lane"] = lane
    if preferred:
        pack["combo_preferred_mode"] = preferred
    if family:
        pack["combo_prompt_family"] = family
    pack["combo_policy"] = "h3_max_effect_combo_v1"
    return pack


def resolve_h3_mode(
    shot: dict[str, Any],
    *,
    intent: dict[str, Any] | None = None,
    has_still: bool | None = None,
    has_last: bool | None = None,
    wants_continue: bool | None = None,
) -> dict[str, Any]:
    """Pick H3 mode for max effect; annotate with combo-eval lane winners for plan/run."""
    pack = resolve_h3_mode_core(
        shot,
        intent=intent,
        has_still=has_still,
        has_last=has_last,
        wants_continue=wants_continue,
    )
    sh = shot if isinstance(shot, dict) else {}
    intent_d = intent if isinstance(intent, dict) else {}
    still_flag = bool(has_still) if has_still is not None else False
    lane = infer_combo_lane(sh, intent=intent_d, has_still=still_flag)
    return annotate_combo_resolve(pack, lane=lane)

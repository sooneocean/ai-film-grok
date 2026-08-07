#!/usr/bin/env python3
"""Shot generation lane projection — single read-only exit for agent/dispatch.

Maps each shot to a coarse production lane + H3 mode suggestion + gate list.
Does not submit GPU work. Built on h3_mode + anatomy_safety (thin wrapper).

Lanes:
  setup | dialogue_safe | dialogue_restricted | meat | insert | env
  | continue | poison_blocked | still_challenge | reaction
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from util import read_json

LANES = frozenset(
    {
        "setup",
        "dialogue_safe",
        "dialogue_restricted",
        "meat",
        "insert",
        "env",
        "continue",
        "poison_blocked",
        "still_challenge",
        "reaction",
    }
)

_STILL_RECIPES = {
    "setup": "grok_or_qwen_hero_still_fill_ge_75",
    "dialogue_safe": "speaker_face_mcu_state_photo",
    "dialogue_restricted": "qwen_state_photo_anatomy_safe",
    "meat": "undress_anchor_or_state_anatomy_safe",
    "insert": "detail_l4_still",
    "env": "optional_or_t2v_no_face",
    "continue": "approved_endframe_handoff",
    "poison_blocked": "archive_then_qwen_or_still_challenge",
    "still_challenge": "frw_i2i_or_qwen_edit_candidate",
    "reaction": "reaction_state_still",
}

_AUDIO = {
    "setup": "edge_or_native",
    "dialogue_safe": "prefer_native",
    "dialogue_restricted": "prefer_native",
    "meat": "prefer_native_plus_sex_sfx",
    "insert": "foley",
    "env": "ambience",
    "continue": "inherit",
    "poison_blocked": "none",
    "still_challenge": "none",
    "reaction": "silence_or_ambience",
}


def _root(path: Path | str) -> Path:
    return Path(path).expanduser().resolve()


def _load_spec(root: Path) -> dict[str, Any]:
    spec = read_json(root / "film-spec.json") or {}
    return spec if isinstance(spec, dict) else {}


def _load_manifest(root: Path) -> dict[str, Any]:
    man = read_json(root / "manifest.json") or {}
    return man if isinstance(man, dict) else {}


def _iter_shots(spec: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for scene in spec.get("scenes") or []:
        if not isinstance(scene, dict):
            continue
        for sh in scene.get("shots") or []:
            if isinstance(sh, dict) and sh.get("id"):
                out.append(sh)
    if not out and isinstance(spec.get("shots"), list):
        out = [s for s in spec["shots"] if isinstance(s, dict) and s.get("id")]
    return out


def _find_shot(spec: dict[str, Any], shot_id: str) -> dict[str, Any] | None:
    sid = str(shot_id)
    for sh in _iter_shots(spec):
        if str(sh.get("id") or "") == sid:
            return sh
    return None


def still_record(root: Path, shot_id: str) -> dict[str, Any] | None:
    man = _load_manifest(root)
    stills = man.get("stills") if isinstance(man.get("stills"), dict) else {}
    rec = stills.get(str(shot_id))
    return rec if isinstance(rec, dict) else None


def is_poison_blocked(root: Path | str, shot_id: str, *, shot: dict[str, Any] | None = None) -> bool:
    """True when still is known poison / rejected — never queue I2V.

    Aligns with fill-idle poison + anatomy_safe=false (harder than status-only).
    """
    base = _root(root)
    sid = str(shot_id)
    still = still_record(base, sid)
    if isinstance(still, dict):
        status = str(still.get("status") or "").lower()
        if status in {"poison", "rejected", "blocked"}:
            return True
        if still.get("poison") is True or still.get("anatomy_poison") is True:
            return True
        if still.get("anatomy_safe") is False:
            return True
    poison_dir = base / "receipts" / "poison"
    if poison_dir.is_dir():
        for p in poison_dir.glob(f"*{sid}*"):
            if p.is_file():
                return True
    # optional shot-level flag
    if isinstance(shot, dict) and (
        shot.get("poison") is True or shot.get("anatomy_poison") is True
    ):
        return True
    return False


def missing_anatomy_attestation(
    root: Path | str,
    shot_id: str,
    *,
    shot: dict[str, Any] | None = None,
) -> bool:
    """True when an **approved** restricted still lacks anatomy_safe=true.

    No still / unapproved still → False here (other gates handle missing keyframe).
    anatomy_safe=false is also poison via ``is_poison_blocked``.
    """
    base = _root(root)
    try:
        from anatomy_safety import shot_requires_anatomy_safety
    except Exception:
        return False
    if not shot_requires_anatomy_safety(base, str(shot_id), shot=shot):
        return False
    still = still_record(base, str(shot_id))
    if not isinstance(still, dict):
        return False
    if still.get("status") != "approved":
        return False
    if still.get("anatomy_safe") is False:
        return False  # poison path owns this
    return still.get("anatomy_safe") is not True


def _spoken(shot: dict[str, Any], intent: dict[str, Any] | None) -> str:
    try:
        from h3_mode import spoken_text_of

        return spoken_text_of(shot, intent)
    except Exception:
        pass
    return str(shot.get("spoken_text") or "").strip()


def _screen(shot: dict[str, Any], intent: dict[str, Any] | None) -> str:
    try:
        from h3_mode import screen_mode_of

        return screen_mode_of(shot, intent)
    except Exception:
        return str(shot.get("screen_mode") or "").strip().lower()


def _is_restricted(shot: dict[str, Any], intent: dict[str, Any] | None) -> bool:
    if isinstance(intent, dict) and intent.get("content_class") == "restricted_local":
        return True
    try:
        from anatomy_safety import shot_is_restricted

        return shot_is_restricted(shot)
    except Exception:
        heat = str(shot.get("heat_phase") or "").strip().lower()
        wardrobe = str(shot.get("wardrobe_state") or "").strip().lower()
        return heat in {"foreplay", "act", "climax"} or wardrobe in {
            "partial",
            "undressed",
            "bare",
            "nude",
        }


def _wants_continue(shot: dict[str, Any]) -> bool:
    try:
        from h3_mode import wants_continue_shot

        return wants_continue_shot(shot)
    except Exception:
        dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
        chain = str(dsl.get("chain_mode") or shot.get("chain_mode") or "").strip().lower()
        return chain == "continue" or bool(str(shot.get("parent_shot_id") or "").strip())


def _role(shot: dict[str, Any], intent: dict[str, Any] | None) -> str:
    if isinstance(intent, dict):
        r = str(intent.get("shot_role") or "").strip().lower()
        if r:
            return r
    return str(shot.get("shot_role") or "hero").strip().lower()


def _size_token(shot: dict[str, Any]) -> str:
    try:
        from h3_mode import shot_size_token

        return shot_size_token(shot)
    except Exception:
        return str(shot.get("shot_size") or "").strip().lower()


def _dramatic(shot: dict[str, Any]) -> str:
    return str(shot.get("dramatic_function") or "").strip().lower()


def _gates_for(
    lane: str,
    *,
    restricted: bool,
    on_camera_dialogue: bool,
) -> list[str]:
    gates = ["composition_fill", "true_video", "motion_core"]
    if lane == "poison_blocked":
        return ["anatomy_poison_archive", "still_challenge_or_qwen", "re_attest_anatomy_safe"]
    if lane == "still_challenge":
        return ["still_challenge_promote", "anatomy_safe_if_restricted", "composition_fill"]
    if lane == "env":
        return ["no_face_on_t2v", "motion_core_soft"]
    if restricted or lane in {"meat", "dialogue_restricted"}:
        gates.append("anatomy_safe")
        gates.append("no_redress")
    if on_camera_dialogue or lane in {"dialogue_safe", "dialogue_restricted"}:
        gates.append("speaker_frame")
        gates.append("dialogue_inject")
        gates.append("native_xor_tts")
    if lane == "meat":
        gates.append("variety_precheck")
        gates.append("high_motion_mean")
    if lane == "continue":
        gates.append("endframe_handoff")
        gates.append("endframe_anatomy_if_restricted")
    if lane == "insert":
        gates.append("detail_still_preferred")
    return gates


def resolve_shot_lane(
    shot: dict[str, Any],
    *,
    root: Path | str | None = None,
    intent: dict[str, Any] | None = None,
    has_still: bool | None = None,
    has_last: bool | None = None,
    profile: str | None = None,
) -> dict[str, Any]:
    """Pure-ish resolve: prefer providing root for poison/manifest checks."""
    sh = shot if isinstance(shot, dict) else {}
    sid = str(sh.get("id") or "")
    intent = intent if isinstance(intent, dict) else {}
    base = _root(root) if root is not None else None

    poison = False
    miss_anatomy = False
    if base is not None and sid:
        poison = is_poison_blocked(base, sid, shot=sh)
        if not poison:
            miss_anatomy = missing_anatomy_attestation(base, sid, shot=sh)

    role = _role(sh, intent)
    spoken = _spoken(sh, intent)
    screen = _screen(sh, intent)
    on_cam = bool(spoken) and screen in {"on_camera", "on-camera", ""}
    off_cam = bool(spoken) and screen in {"off_camera", "off-camera"}
    restricted = _is_restricted(sh, intent)
    cont = _wants_continue(sh)
    size = _size_token(sh)
    df = _dramatic(sh)
    heat = str(
        intent.get("heat_phase") or sh.get("heat_phase") or ""
    ).strip().lower()

    # still_challenge is a repair path, not a primary lane (hint only when fill-idle says so)
    still_challenge_hint = False

    blocked_by: list[str] = []
    lane = "setup"
    reasons: list[str] = []

    if poison:
        lane = "poison_blocked"
        reasons.append("poison_or_anatomy_safe_false")
        blocked_by.append("POISON_STILL_BLOCKS_I2V")
    elif cont:
        lane = "continue"
        reasons.append("chain_mode_continue")
        if miss_anatomy and restricted:
            blocked_by.append("ANATOMY_STILL_NOT_SAFE")
            reasons.append("continue_needs_anatomy_safe_source")
    elif role in {"env", "bridge"} or df in {"env", "bridge", "establishing_env"}:
        lane = "env"
        reasons.append("faceless_env")
    elif role == "insert" or size in {"l4", "insert_l4", "ecu", "extreme_close"} or df in {
        "insert",
        "sensory",
        "detail",
    }:
        # insert before meat so L4 contact stays insert lane
        if restricted and heat in {"act", "climax"} and size in {"l4", "insert_l4", "ecu"}:
            lane = "insert"
            reasons.append("detail_insert")
        elif restricted and not spoken:
            lane = "meat" if heat in {"act", "climax", "foreplay"} else "insert"
            reasons.append("insert_or_meat")
        else:
            lane = "insert"
            reasons.append("insert_detail")
    elif on_cam and spoken:
        lane = "dialogue_restricted" if restricted else "dialogue_safe"
        reasons.append("on_camera_dialogue")
        if miss_anatomy and restricted:
            blocked_by.append("ANATOMY_STILL_NOT_SAFE")
    elif off_cam and spoken:
        lane = "dialogue_restricted" if restricted else "dialogue_safe"
        reasons.append("off_camera_dialogue")
    elif restricted and heat in {"act", "climax", "foreplay", "afterglow"}:
        if df in {"reaction", "silence"} or screen in {"silence", "reaction", "action_cover"}:
            lane = "reaction"
            reasons.append("meat_adjacent_reaction")
        else:
            lane = "meat"
            reasons.append("restricted_meat")
        if miss_anatomy:
            blocked_by.append("ANATOMY_STILL_NOT_SAFE")
    elif screen in {"silence", "reaction", "action_cover"} or df in {
        "reaction",
        "silence",
        "action_cover",
    }:
        lane = "reaction"
        reasons.append("coverage_reaction")
    else:
        lane = "setup"
        reasons.append("setup_or_soft_hero")

    if still_challenge_hint and lane not in {"poison_blocked", "env"}:
        # soft overlay — generation path still uses primary lane for mode
        reasons.append("still_challenge_hint")

    # Mode via h3_mode (source of truth)
    if has_still is None and base is not None and sid:
        try:
            from h3_workflow import _approved_still

            has_still = _approved_still(base, sid) is not None
        except Exception:
            has_still = False
    if has_still is None:
        has_still = False
    if has_last is None and base is not None and sid:
        try:
            from h3_media_pack import resolve_last_frame_path

            lp, _ = resolve_last_frame_path(base, sid, shot=sh)
            has_last = bool(lp is not None and lp.is_file())
        except Exception:
            has_last = False
    if has_last is None:
        has_last = False

    mode_res: dict[str, Any] = {}
    if lane == "poison_blocked":
        mode_res = {
            "mode": None,
            "alt_mode": None,
            "reasons": ["poison_blocks_motion"],
            "weapon_id": None,
        }
    else:
        try:
            from h3_mode import resolve_h3_mode

            mode_res = resolve_h3_mode(
                sh,
                intent=intent or None,
                has_still=bool(has_still),
                has_last=bool(has_last),
                wants_continue=cont,
            )
        except Exception as exc:
            mode_res = {
                "mode": "i2v" if has_still else "t2v",
                "alt_mode": None,
                "reasons": [f"mode_fallback:{exc}"[:80]],
                "weapon_id": None,
            }

    # Insert without still: prefer hint over silent genital T2V
    if lane == "insert" and not has_still:
        if mode_res.get("block_code") == "INSERT_NEEDS_DETAIL_STILL" or mode_res.get(
            "blocked"
        ):
            blocked_by.append("INSERT_NEEDS_DETAIL_STILL")
            reasons.append("insert_needs_detail_still")
        elif mode_res.get("mode") == "t2v":
            blocked_by.append("INSERT_NEEDS_DETAIL_STILL")
            reasons.append("insert_no_still_hint")
        elif restricted:
            blocked_by.append("INSERT_NEEDS_DETAIL_STILL")
            reasons.append("insert_restricted_needs_still")

    gates = _gates_for(
        lane,
        restricted=restricted,
        on_camera_dialogue=bool(on_cam and spoken),
    )
    if "ANATOMY_STILL_NOT_SAFE" in blocked_by and "anatomy_safe" not in gates:
        gates.append("anatomy_safe")

    i2v_ok = (
        lane != "poison_blocked"
        and "ANATOMY_STILL_NOT_SAFE" not in blocked_by
        and "INSERT_NEEDS_DETAIL_STILL" not in blocked_by
    )
    if lane == "poison_blocked":
        i2v_ok = False

    promote_policy = "human_pk_no_mean_only"
    if lane == "poison_blocked":
        promote_policy = "ban_until_anatomy_safe"
    elif lane == "still_challenge":
        promote_policy = "human_promote_candidate"

    profile_norm = str(profile or "").strip() or None
    if profile_norm is None and base is not None:
        try:
            from film_spec_profile import resolve_i2v_profile

            profile_norm = str(resolve_i2v_profile() or "h3_primary")
        except Exception:
            profile_norm = "h3_primary"
        # film-spec override
        try:
            spec = _load_spec(base)
            for key in ("_i2v_profile", "i2v_profile", "AIFILM_I2V_PROFILE"):
                v = str(spec.get(key) or "").strip()
                if v:
                    profile_norm = v
                    break
        except Exception:
            pass

    return {
        "schema_version": 1,
        "kind": "ai-film-shot-lane",
        "shot_id": sid or None,
        "lane": lane,
        "reasons": reasons,
        "blocked_by": blocked_by,
        "i2v_allowed": bool(i2v_ok),
        "h3_mode": mode_res.get("mode"),
        "h3_alt_mode": mode_res.get("alt_mode"),
        "h3_mode_reasons": list(mode_res.get("reasons") or []),
        "weapon_id": mode_res.get("weapon_id"),
        "still_recipe": _STILL_RECIPES.get(lane),
        "audio_lane": _AUDIO.get(lane),
        "required_gates": gates,
        "promote_policy": promote_policy,
        "restricted": bool(restricted),
        "on_camera_dialogue": bool(on_cam and spoken),
        "wants_continue": bool(cont),
        "shot_role": role,
        "has_still": bool(has_still),
        "has_last": bool(has_last),
        "still_challenge_hint": bool(still_challenge_hint),
        "profile": profile_norm,
        "command": (
            None
            if not i2v_ok or not mode_res.get("mode")
            else (
                f'aifilm h3 run --root "<film>" --shot-id {sid} '
                f'--mode {mode_res.get("mode")} --register'
                if sid
                else None
            )
        ),
    }


def resolve_film_shot_lanes(
    root: Path | str,
    *,
    shot_id: str | None = None,
    profile: str | None = None,
) -> dict[str, Any]:
    """Project all (or one) shots for a film root."""
    base = _root(root)
    spec = _load_spec(base)
    shots = _iter_shots(spec)
    if shot_id:
        one = _find_shot(spec, shot_id)
        shots = [one] if one else []
    rows: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    blocked = 0
    for sh in shots:
        intent = None
        try:
            from production_router import build_shot_intent

            intent = build_shot_intent(spec, sh)
        except Exception:
            intent = None
        row = resolve_shot_lane(
            sh,
            root=base,
            intent=intent,
            profile=profile,
        )
        rows.append(row)
        lane = str(row.get("lane") or "unknown")
        counts[lane] = counts.get(lane, 0) + 1
        if row.get("blocked_by") or not row.get("i2v_allowed"):
            blocked += 1

    return {
        "schema_version": 1,
        "kind": "ai-film-shot-lane-report",
        "ok": True,
        "root": str(base),
        "shot_count": len(rows),
        "blocked_count": blocked,
        "lane_counts": counts,
        "shots": rows,
    }


__all__ = [
    "LANES",
    "is_poison_blocked",
    "missing_anatomy_attestation",
    "resolve_film_shot_lanes",
    "resolve_shot_lane",
    "still_record",
]

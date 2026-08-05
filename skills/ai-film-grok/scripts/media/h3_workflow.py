#!/usr/bin/env python3
"""End-to-end MiniMax H3 local motion lane for hybrid_h3 / comfy-h3 films.

Closes the gap between armory pilot weapons and film production:
plan → generate on 5090 → optional silent plate → queue complete → register-clip.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from h3_mode import effect_tips as _h3_effect_tips
from h3_mode import resolve_h3_mode
from production_router import build_shot_intent
from util import read_json, sha256_file, write_json


class H3WorkflowError(RuntimeError):
    pass


_H3_ENDPOINTS = frozenset(
    {
        "local_minimax_h3_t2v",
        "local_minimax_h3_i2v",
        "local_minimax_h3_r2v",
    }
)


def _root(path: Path | str) -> Path:
    return Path(path).expanduser().resolve()


def _load_spec(root: Path) -> dict[str, Any]:
    data = read_json(root / "film-spec.json")
    if not isinstance(data, dict):
        raise H3WorkflowError("film-spec.json is missing or invalid")
    return data


def _iter_shots(spec: dict[str, Any]) -> list[dict[str, Any]]:
    shots: list[dict[str, Any]] = []
    for scene in spec.get("scenes") or []:
        if not isinstance(scene, dict):
            continue
        for shot in scene.get("shots") or []:
            if isinstance(shot, dict) and shot.get("id"):
                shots.append(shot)
    return shots


def _find_shot(spec: dict[str, Any], shot_id: str) -> dict[str, Any]:
    for shot in _iter_shots(spec):
        if str(shot.get("id")) == shot_id:
            return shot
    raise H3WorkflowError(f"shot not found in film-spec: {shot_id}")


def _approved_still(root: Path, shot_id: str) -> Path | None:
    manifest = read_json(root / "manifest.json") or {}
    stills = manifest.get("stills") if isinstance(manifest, dict) else {}
    still = stills.get(shot_id) if isinstance(stills, dict) else None
    if not isinstance(still, dict):
        # common layout stills/<id>.png
        for candidate in (
            root / "stills" / f"{shot_id}.png",
            root / "keyframes" / f"{shot_id}.png",
            root / "stills" / f"{shot_id}.jpg",
        ):
            if candidate.is_file():
                return candidate
        return None
    raw = still.get("path") or still.get("file")
    if not raw:
        return None
    path = Path(str(raw))
    if not path.is_absolute():
        path = root / path
    return path if path.is_file() else None


def _shot_wants_continue(shot: dict[str, Any]) -> bool:
    """True when this shot is an endframe-continue link."""
    from continue_handoff import shot_wants_continue

    return shot_wants_continue(shot)


def _previous_shot_id(spec: dict[str, Any], shot_id: str, shot: dict[str, Any]) -> str | None:
    from continue_handoff import previous_shot_id

    return previous_shot_id(spec, shot_id, shot)


def resolve_continue_handoff(
    root: Path | str,
    shot_id: str,
    *,
    shot: dict[str, Any] | None = None,
    spec: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Phase C · Read previous-shot continue handoff (shared H3+Grok module)."""
    from continue_handoff import resolve_continue_handoff as _resolve

    if not isinstance(spec, dict):
        try:
            spec = _load_spec(_root(root))
        except H3WorkflowError:
            spec = {}
    if not isinstance(shot, dict):
        try:
            shot = _find_shot(spec, shot_id) if spec else {}
        except H3WorkflowError:
            shot = {}
    return _resolve(root, shot_id, shot=shot, spec=spec)


def _spoken_dialogue_text(shot: dict[str, Any]) -> str:
    """Extract the spoken dialogue line for a shot's audio_cues, if any."""
    from motion_prompt_spine import spoken_dialogue_text

    return spoken_dialogue_text(shot)


def _prompt_for_shot(
    root: Path,
    shot: dict[str, Any],
    *,
    mode: str,
    spec: dict[str, Any] | None = None,
) -> str:
    """Build H3 motion prompt with shared film-core spine (DF/want/camera/dialogue)."""
    from motion_prompt_spine import (
        MotionCoreError,
        assert_motion_prompt_core,
        build_motion_prompt,
        ensure_motion_core_in_prompt,
        provider_prefix,
    )

    if isinstance(spec, dict):
        film = spec
    else:
        try:
            film = _load_spec(root)
        except H3WorkflowError:
            # Unit tests / prompt-only calls may lack film-spec; spine still works.
            film = {}
    sid = str(shot.get("id") or "shot")
    prompt_paths = [
        root / "receipts" / "prompts" / f"{sid}.i2v.txt",
        root / "receipts" / "prompts" / f"{sid}.txt",
        root / "prompts" / f"{sid}.txt",
    ]
    author = ""
    for path in prompt_paths:
        if path.is_file():
            text = path.read_text(encoding="utf-8").strip()
            if text:
                author = text
                break
    if author:
        # Keep author geometry/style; merge missing DF/want/dialogue/camera.
        body = ensure_motion_core_in_prompt(author, film, shot)
        # If author file had no geometry prefix, leave as-is; spine already has content.
        if not any(
            k in body.lower()
            for k in ("vertical 9:16", "picture 1", "text-to-video", "animate the start")
        ):
            prompt = f"{provider_prefix(mode)} {body}".strip()
        else:
            prompt = body
    else:
        prompt = build_motion_prompt(film, shot, mode=mode, include_provider_prefix=True)
    try:
        assert_motion_prompt_core(
            prompt,
            shot,
            mode=mode,
            role=str(shot.get("shot_role") or "hero"),
        )
    except MotionCoreError as exc:
        raise H3WorkflowError(str(exc)) from exc
    return prompt


def plan_h3_shot(
    root: Path | str,
    shot_id: str,
    *,
    still_override: Path | str | None = None,
    last_override: Path | str | None = None,
    refs_override: list[Path | str] | None = None,
) -> dict[str, Any]:
    """Return a machine-readable H3 execution plan for one shot."""
    from h3_media_pack import resolve_media_pack

    base = _root(root)
    spec = _load_spec(base)
    shot = _find_shot(spec, shot_id)
    intent = build_shot_intent(spec, shot)
    h3 = spec.get("h3") if isinstance(spec.get("h3"), dict) else {}
    plan_core = {
        "dramatic_function": intent.get("dramatic_function"),
        "want_beat": intent.get("want_beat"),
        "motion_tier": intent.get("motion_tier"),
        "spoken_text": intent.get("spoken_text"),
        "has_action_core": intent.get("has_action_core"),
    }
    approved = _approved_still(base, shot_id)
    cont = resolve_continue_handoff(base, shot_id, shot=shot, spec=spec)
    media_pack = resolve_media_pack(
        base,
        shot_id,
        shot=shot,
        still_override=still_override,
        last_override=last_override,
        approved_still=approved,
        continue_end_frame=cont.get("end_frame"),
        wants_continue=bool(cont.get("wants_continue")),
        refs_override=refs_override,
    )
    first = media_pack.get("first") if isinstance(media_pack.get("first"), dict) else None
    last = media_pack.get("last") if isinstance(media_pack.get("last"), dict) else None
    still: Path | None = Path(str(first["path"])) if first and first.get("path") else None
    still_source: str | None = str(first.get("source")) if first else None
    last_path: Path | None = Path(str(last["path"])) if last and last.get("path") else None
    last_source: str | None = str(last.get("source")) if last else None
    if still is None:
        filled = base / "stills" / f"{shot_id}.png"
        if filled.is_file():
            still = filled
            still_source = "stills_after_continue_copy"
            media_pack = resolve_media_pack(
                base,
                shot_id,
                shot=shot,
                still_override=still,
                last_override=last_override,
                approved_still=still,
                continue_end_frame=cont.get("end_frame"),
                wants_continue=bool(cont.get("wants_continue")),
                refs_override=refs_override,
            )
            last = media_pack.get("last") if isinstance(media_pack.get("last"), dict) else None
            last_path = Path(str(last["path"])) if last and last.get("path") else None
            last_source = str(last.get("source")) if last else None
    mode_res = resolve_h3_mode(
        shot,
        intent=intent,
        has_still=still is not None,
        has_last=last_path is not None,
        wants_continue=bool(cont.get("wants_continue")),
    )
    mode = str(mode_res["mode"])
    weapon = str(mode_res["weapon_id"])
    endpoint = str(mode_res["source_endpoint"])
    audio_policy = str(intent.get("audio_policy") or h3.get("audio_policy") or "prefer_native")
    max_dur = float(intent.get("max_duration_sec") or h3.get("max_duration_sec") or 8)
    enabled = bool(intent.get("h3_enabled") or h3.get("enabled") is True)
    alt = mode_res.get("alt_mode")
    last_cli = f' --last-frame "{last_path}"' if last_path and mode in {"flf", "r2v"} else ""
    cmd = f'aifilm h3 run --root "{base}" --shot-id {shot_id} --mode {mode}{last_cli} --register'
    alt_last = (
        f' --last-frame "{last_path}"' if last_path and str(alt or "") in {"flf", "r2v"} else ""
    )
    cmd_alt = (
        f'aifilm h3 run --root "{base}" --shot-id {shot_id} --mode {alt}{alt_last} --register'
        if alt
        else None
    )
    plan: dict[str, Any] = {
        "schema_version": 1,
        "kind": "ai-film-h3-shot-plan",
        "ok": True,
        "shot_id": shot_id,
        "mode": mode,
        "mode_resolve": mode_res,
        "mode_policy": {
            "truth": "h3 list/plan mode is the default truth",
            "follow_command": cmd,
            "alt_when_energy_low": cmd_alt,
            "note": (
                "Do not default whole film to R2V. Use resolve_h3_mode; "
                "CLI --mode only when overriding after pilot/energy fail."
            ),
        },
        "weapon_id": weapon,
        "source_endpoint": endpoint,
        "provider": "comfy-h3",
        "intent": intent,
        "motion_core": plan_core,
        "h3_enabled": enabled,
        "still_path": str(still) if still else None,
        "still_source": still_source,
        "last_path": str(last_path) if last_path else None,
        "last_source": last_source,
        "media_pack": media_pack,
        "ref_paths": [
            str(r["path"])
            for r in (media_pack.get("refs") or [])
            if isinstance(r, dict) and r.get("path")
        ],
        "missing_last_hint": media_pack.get("missing_last_hint"),
        "continue_handoff": cont,
        "requires_still": bool(mode_res.get("requires_still")),
        "requires_last": bool(mode_res.get("requires_last")),
        "audio_policy": audio_policy,
        "max_duration_sec": max_dur,
        "megapixels_draft": float(h3.get("megapixels_draft") or 0.2),
        "allow_bulk": bool(h3.get("allow_bulk")),
        "command": cmd,
        "command_alt": cmd_alt,
        "effect_tips": _h3_effect_tips(mode, mode_res),
        "combo_lane": mode_res.get("combo_lane"),
        "combo_preferred_mode": mode_res.get("combo_preferred_mode"),
        "combo_prompt_family": mode_res.get("combo_prompt_family"),
        "still_challenge_candidates": _still_challenge_candidates(base, shot_id),
    }
    # Material fidelity: unified GenerationRequest receipt (StillSource + prompt + refs)
    try:
        from generation_request import build_generation_request

        gen_kind = str(mode) if str(mode) in {"i2v", "flf", "r2v", "t2v"} else "i2v"
        gen_req = build_generation_request(
            base,
            shot_id,
            kind=gen_kind,
            still_override=still_override,
            last_override=last_override,
            refs_override=refs_override,
            write=True,
        )
        plan["generation_request"] = {
            "ok": gen_req.get("ok"),
            "text_sha256": gen_req.get("text_sha256"),
            "image_ref_count": len(gen_req.get("image_refs") or []),
            "still_source": (gen_req.get("still_source") or {}).get("source"),
            "receipt": f"receipts/prompts/{shot_id}.request.json",
            "constraints": gen_req.get("constraints") or [],
        }
    except Exception as exc:  # noqa: BLE001 — plan must not die on optional receipt
        plan["generation_request"] = {"ok": False, "error": str(exc)[:200]}
    return plan


def _still_challenge_candidates(root: Path, shot_id: str) -> list[dict[str, Any]]:
    try:
        from still_challenge import list_candidates

        return list_candidates(root, shot_id)
    except Exception:  # noqa: BLE001
        return []


def _strip_audio(src: Path, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(src),
        "-an",
        "-c:v",
        "copy",
        str(dest),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0 or not dest.is_file():
        # re-encode fallback if stream copy fails
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(src),
            "-an",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(dest),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0 or not dest.is_file():
        raise H3WorkflowError(f"failed to strip H3 native audio: {proc.stderr[:300]}")
    return dest


def _native_audio_usable(path: Path, *, min_db: float = -42.0) -> tuple[bool, dict[str, Any]]:
    """Return whether H3 native audio is present and audible enough to keep."""
    meta: dict[str, Any] = {"has_audio": False, "mean_volume_db": None, "usable": False}
    try:
        from media_qa import analyze_media

        qa = analyze_media(path, require_audio=False, require_motion=False)
        has_audio = bool(qa.get("has_audio"))
        meta["has_audio"] = has_audio
        if not has_audio:
            return False, meta
    except Exception as exc:  # noqa: BLE001
        meta["probe_error"] = str(exc)[:200]
        return False, meta

    # volumedetect on the embedded audio stream (no full re-encode)
    proc = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-i",
            str(path),
            "-vn",
            "-af",
            "volumedetect",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    mean_db: float | None = None
    for line in (proc.stderr or "").splitlines():
        if "mean_volume:" in line:
            try:
                mean_db = float(line.split("mean_volume:")[1].split("dB")[0].strip())
            except (IndexError, ValueError):
                mean_db = None
            break
    meta["mean_volume_db"] = mean_db
    usable = mean_db is not None and mean_db > min_db
    # If volumedetect failed but a stream exists, keep native (H3 usually has real audio).
    if mean_db is None and has_audio:
        usable = True
        meta["usable_reason"] = "has_audio_stream_volume_unknown"
    meta["usable"] = usable
    return usable, meta


# Delivery geometry floor for 9:16 short-form (matches keyframe / motion gate).
_H3_MIN_WIDTH = 704
_H3_MIN_HEIGHT = 1280


def ensure_h3_delivery_geometry(
    src: Path,
    dest: Path,
    *,
    min_width: int = _H3_MIN_WIDTH,
    min_height: int = _H3_MIN_HEIGHT,
) -> dict[str, Any]:
    """Upscale H3 output to ≥704×1280 9:16 when the local model emits small frames.

    H3 film-lane canaries historically decode near 352×608; register/final gates
    expect short-form floor geometry. Deterministic scale+pad, no crop of heads.
    """
    src = Path(src).expanduser().resolve()
    dest = Path(dest).expanduser().resolve()
    meta: dict[str, Any] = {
        "ok": True,
        "source": str(src),
        "upscaled": False,
        "min_width": min_width,
        "min_height": min_height,
    }
    if not src.is_file():
        raise H3WorkflowError(f"H3 geometry source missing: {src}")
    width = height = 0
    try:
        from media_qa import analyze_media

        qa = analyze_media(src, require_audio=False, require_motion=False)
        width = int(qa.get("width") or 0)
        height = int(qa.get("height") or 0)
    except Exception as exc:  # noqa: BLE001
        meta["probe_error"] = str(exc)[:200]
        meta["deliver_path"] = str(src)
        meta["width"] = width
        meta["height"] = height
        return meta
    meta["width"] = width
    meta["height"] = height
    if width >= min_width and height >= min_height:
        meta["deliver_path"] = str(src)
        meta["reason"] = "already_meets_floor"
        return meta
    dest.parent.mkdir(parents=True, exist_ok=True)
    vf = (
        f"scale={min_width}:{min_height}:force_original_aspect_ratio=decrease,"
        f"pad={min_width}:{min_height}:(ow-iw)/2:(oh-ih)/2:color=black"
    )
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(src),
        "-vf",
        vf,
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "copy",
        str(dest),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0 or not dest.is_file():
        cmd_a = [
            "ffmpeg",
            "-y",
            "-i",
            str(src),
            "-vf",
            vf,
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            str(dest),
        ]
        proc = subprocess.run(cmd_a, capture_output=True, text=True, check=False)
    if proc.returncode != 0 or not dest.is_file():
        raise H3WorkflowError(f"H3 geometry upscale failed: {(proc.stderr or '')[:300]}")
    meta["upscaled"] = True
    meta["deliver_path"] = str(dest)
    meta["upscaled_path"] = str(dest)
    meta["reason"] = f"upscaled_from_{width}x{height}"
    try:
        from media_qa import analyze_media

        qa2 = analyze_media(dest, require_audio=False, require_motion=False)
        meta["width"] = int(qa2.get("width") or min_width)
        meta["height"] = int(qa2.get("height") or min_height)
    except Exception:  # noqa: BLE001
        meta["width"] = min_width
        meta["height"] = min_height
    return meta


def resolve_h3_deliver_audio(
    raw_path: Path,
    plate_path: Path,
    *,
    audio_policy: str,
) -> dict[str, Any]:
    """Decide deliver path: keep native when policy + usability allow."""
    policy = (audio_policy or "prefer_native").strip()
    if policy not in {
        "prefer_native",
        "keep_native",
        "strip_native_use_tts_bgm",
        "mute_native",
    }:
        policy = "prefer_native"

    if policy in {"strip_native_use_tts_bgm", "mute_native"}:
        _strip_audio(raw_path, plate_path)
        return {
            "deliver_path": plate_path,
            "audio_stripped": True,
            "audio_policy": policy,
            "audio_policy_effective": policy,
            "use_clip_audio": False,
            "native_audio_meta": {"usable": False, "forced_strip": True},
        }

    if policy == "keep_native":
        return {
            "deliver_path": raw_path,
            "audio_stripped": False,
            "audio_policy": policy,
            "audio_policy_effective": policy,
            "use_clip_audio": True,
            "native_audio_meta": {"usable": True, "forced_keep": True},
        }

    # prefer_native: keep when usable, else silent plate for TTS/BGM path
    usable, meta = _native_audio_usable(raw_path)
    if usable:
        return {
            "deliver_path": raw_path,
            "audio_stripped": False,
            "audio_policy": policy,
            "audio_policy_effective": "keep_native",
            "use_clip_audio": True,
            "native_audio_meta": meta,
        }
    _strip_audio(raw_path, plate_path)
    return {
        "deliver_path": plate_path,
        "audio_stripped": True,
        "audio_policy": policy,
        "audio_policy_effective": "strip_native_use_tts_bgm",
        "use_clip_audio": False,
        "native_audio_meta": meta,
    }


def _write_continue_handoff(
    root: Path,
    *,
    shot_id: str,
    shot: dict[str, Any],
    deliver: Path,
    mode: str,
    seed: int,
) -> dict[str, Any]:
    """Extract end frame + dramatic packet (shared continue_handoff module)."""
    from continue_handoff import write_continue_handoff

    return write_continue_handoff(
        root,
        shot_id=shot_id,
        deliver=deliver,
        shot=shot,
        mode=mode,
        engine="h3",
        seed=seed,
    )


def run_h3_shot(
    root: Path | str,
    shot_id: str,
    *,
    mode: str | None = None,
    register: bool = False,
    status: str = "candidate",
    allow_experimental: bool | None = None,
    seed: int = 20260803,
    timeout_sec: int = 1800,
    enqueue_queue: bool = True,
    production_stage: str | None = None,
    still_override: Path | str | None = None,
    last_override: Path | str | None = None,
    refs_override: list[Path | str] | None = None,
) -> dict[str, Any]:
    """Generate one H3 clip for a film shot and optionally register it."""
    from h3_media_pack import flf_prompt_clause, r2v_ref_prompt_clause
    from h3_mode import H3_MODE_ENDPOINT, H3_MODE_WEAPON

    base = _root(root)
    plan = plan_h3_shot(
        base,
        shot_id,
        still_override=still_override,
        last_override=last_override,
        refs_override=refs_override,
    )
    stage = (production_stage or "production").strip().lower()
    if allow_experimental is None:
        allow_experimental = stage == "pilot"
    if mode:
        mode_norm = mode.strip().lower()
        if mode_norm not in {"t2v", "i2v", "flf", "r2v"}:
            raise H3WorkflowError("mode must be t2v, i2v, flf, or r2v")
        if mode_norm == "flf" and not plan.get("last_path"):
            raise H3WorkflowError(
                f"H3 flf requires a last frame for {shot_id} "
                f"(--last-frame or stills/{shot_id}_end.png)"
            )
        resolved = str(plan.get("mode") or "")
        plan["mode"] = mode_norm
        plan["weapon_id"] = H3_MODE_WEAPON[mode_norm]
        plan["source_endpoint"] = H3_MODE_ENDPOINT[mode_norm]
        plan["requires_still"] = mode_norm in {"i2v", "flf", "r2v"}
        plan["requires_last"] = mode_norm == "flf"
        # Record CLI override vs list/plan truth (energy/pilot recovery only)
        if resolved and mode_norm != resolved:
            plan["mode_cli_override"] = {
                "resolved": resolved,
                "cli": mode_norm,
                "note": "CLI --mode overrode h3 list/plan resolve; prefer resolve unless energy fail",
            }

    if plan["requires_still"] and not plan.get("still_path"):
        raise H3WorkflowError(
            f"H3 {plan['mode']} requires an approved still/keyframe for {shot_id}"
        )
    if plan.get("requires_last") and not plan.get("last_path"):
        raise H3WorkflowError(
            f"H3 flf requires last frame for {shot_id} (--last-frame or stills/{shot_id}_end.png)"
        )

    # Variety door when registering candidates (bulk path) — skip via env escape.
    if register:
        from workflow_pack import WorkflowPackError, assert_variety_preflight

        try:
            assert_variety_preflight(base, require=True)
        except WorkflowPackError as exc:
            raise H3WorkflowError(str(exc)) from exc

    spec = _load_spec(base)
    shot = _find_shot(spec, shot_id)
    prompt = _prompt_for_shot(base, shot, mode=str(plan["mode"]), spec=spec)
    if plan["mode"] == "flf":
        clause = flf_prompt_clause()
        if "first-last-frame" not in prompt.lower() and "last keyframe" not in prompt.lower():
            prompt = f"{prompt.rstrip()} {clause}"
    if plan["mode"] == "r2v":
        pack_refs: list[dict[str, Any]] = []
        # First-last R2V: last pose land ref first, then identity/style refs.
        if plan.get("last_path"):
            pack_refs.append(
                {"path": plan["last_path"], "role": "pose", "source": "last_as_pose_ref"}
            )
        mp = plan.get("media_pack") if isinstance(plan.get("media_pack"), dict) else {}
        for ref in list(mp.get("refs") or []):
            if not isinstance(ref, dict):
                continue
            p = str(ref.get("path") or "")
            if (
                plan.get("last_path")
                and p
                and Path(p).resolve() == Path(str(plan["last_path"])).resolve()
            ):
                continue
            pack_refs.append(ref)
        r2v_clause = r2v_ref_prompt_clause(pack_refs)
        if r2v_clause and "<Picture" not in prompt:
            prompt = f"{prompt.rstrip()} {r2v_clause}"
        if plan.get("last_path"):
            land = (
                "First-last reference control: start from the primary still (first frame); "
                "drive motion so the final pose/composition lands on the end pose reference; "
                "preserve identity; do not ignore the end frame."
            )
            if "end pose" not in prompt.lower() and "last keyframe" not in prompt.lower():
                prompt = f"{prompt.rstrip()} {land}"
    prompt_dir = base / "receipts" / "prompts"
    prompt_dir.mkdir(parents=True, exist_ok=True)
    (prompt_dir / f"{shot_id}.h3.spine.txt").write_text(prompt + "\n", encoding="utf-8")
    takes_dir = base / "takes" / shot_id
    takes_dir.mkdir(parents=True, exist_ok=True)
    raw_out = takes_dir / f"{shot_id}_h3_{plan['mode']}_{seed}.mp4"
    plate_out = takes_dir / f"{shot_id}_h3_{plan['mode']}_{seed}_plate.mp4"

    from i2v_provider import LocalComfyH3Provider

    provider = LocalComfyH3Provider()
    keyframe = Path(plan["still_path"]) if plan.get("still_path") else base / "film-spec.json"
    last_frame = (
        Path(plan["last_path"]) if plan.get("last_path") and plan["mode"] == "flf" else None
    )
    gen_kwargs: dict[str, Any] = {
        "keyframe": keyframe,
        "prompt": prompt,
        "out": raw_out,
        "mode": "i2v" if plan["mode"] == "flf" else plan["mode"],
        "seed": seed,
        "timeout_sec": timeout_sec,
        "allow_experimental": bool(allow_experimental),
        "production_stage": stage,
        "filename_prefix": f"aifilm/h3/{shot_id}",
    }
    if last_frame is not None:
        gen_kwargs["last_frame"] = last_frame
    # R2V multi-ref: last (pose land) first, then identity/style (not the primary still).
    if plan["mode"] == "r2v":
        ref_paths: list[Path] = []
        if plan.get("last_path"):
            lp = Path(str(plan["last_path"])).expanduser().resolve()
            if lp.is_file() and lp != keyframe.resolve():
                ref_paths.append(lp)
        for raw in plan.get("ref_paths") or []:
            rp = Path(str(raw)).expanduser().resolve()
            if rp.is_file() and rp != keyframe.resolve() and rp not in ref_paths:
                ref_paths.append(rp)
        if ref_paths:
            gen_kwargs["reference_images"] = ref_paths[:2]  # template slots 21/22
    result = provider.generate(**gen_kwargs)
    if not result.get("ok"):
        raise H3WorkflowError(f"H3 generate failed: {result.get('stderr') or result}")

    # Geometry floor before audio plate decisions (upscale preserves streams when possible).
    geo_out = takes_dir / f"{shot_id}_h3_{plan['mode']}_{seed}_704x1280.mp4"
    geometry = ensure_h3_delivery_geometry(raw_out, geo_out)
    geometry_path = Path(str(geometry.get("deliver_path") or raw_out))

    audio_policy = str(plan.get("audio_policy") or "prefer_native")
    audio_decision = resolve_h3_deliver_audio(geometry_path, plate_out, audio_policy=audio_policy)
    deliver = Path(audio_decision["deliver_path"])
    stripped = bool(audio_decision["audio_stripped"])

    # P2 · dramatic continue handoff (endframe + DF + heat for next shot)
    handoff = _write_continue_handoff(
        base,
        shot_id=shot_id,
        shot=shot,
        deliver=deliver,
        mode=str(plan["mode"]),
        seed=seed,
    )
    use_clip_audio = bool(audio_decision["use_clip_audio"])
    audio_policy_effective = str(audio_decision["audio_policy_effective"])

    receipt = {
        "schema_version": 1,
        "kind": "ai-film-h3-run",
        "ok": True,
        "shot_id": shot_id,
        "plan": plan,
        "provider_result": {
            k: result.get(k) for k in ("ok", "prompt_id", "weapon_id", "source_endpoint", "receipt")
        },
        "raw_path": str(raw_out),
        "raw_sha256": sha256_file(raw_out),
        "geometry": geometry,
        "deliver_path": str(deliver),
        "deliver_sha256": sha256_file(deliver),
        "audio_stripped": stripped,
        "audio_policy": audio_policy,
        "audio_policy_effective": audio_policy_effective,
        "use_clip_audio": use_clip_audio,
        "native_audio_meta": audio_decision.get("native_audio_meta"),
        "prompt_sha256": __import__("hashlib").sha256(prompt.encode("utf-8")).hexdigest(),
        "continue_handoff": handoff,
        "media_pack": plan.get("media_pack"),
        "first_path": plan.get("still_path"),
        "last_path": (plan.get("last_path") if plan.get("mode") in {"flf", "r2v"} else None),
        "input_provenance": result.get("input_provenance"),
    }
    receipt_path = base / "receipts" / f"h3-run-{shot_id}.json"
    write_json(receipt_path, receipt)

    # Fill-Idle PK needs mean sidecars on H3 takes (best-effort; never block run)
    try:
        from i2v_motion_gate import measure_mean_absdiff, write_mean_sidecar

        mean_v = measure_mean_absdiff(deliver)
        if mean_v is not None:
            write_mean_sidecar(deliver, mean_v)
            receipt["mean_absdiff"] = mean_v
            write_json(receipt_path, receipt)
    except Exception as exc:  # noqa: BLE001
        receipt["mean_measure_error"] = str(exc)[:200]
        write_json(receipt_path, receipt)

    queue_job_id = None
    if enqueue_queue:
        try:
            from media_queue import MediaQueue

            mq = MediaQueue(base)
            prompt_file = base / "receipts" / "prompts" / f"{shot_id}.h3.txt"
            prompt_file.parent.mkdir(parents=True, exist_ok=True)
            prompt_file.write_text(prompt, encoding="utf-8")
            # media-queue ops are image_to_video / reference_to_video only (no t2v op).
            # Completion endpoint must match job.operation; real H3 endpoint lives in
            # generation_contract.parameters.source_endpoint for register-clip.
            if plan["mode"] != "t2v" and plan.get("still_path"):
                op = "reference_to_video" if plan["mode"] == "r2v" else "image_to_video"
                inputs = [Path(plan["still_path"])]
                if plan.get("mode") in {"flf", "r2v"} and plan.get("last_path"):
                    inputs.append(Path(str(plan["last_path"])))
                job = mq.add_job(
                    shot_id=shot_id,
                    operation=op,
                    prompt_file=prompt_file,
                    inputs=inputs,
                    allow_without_pilot=True,
                    is_canary=False,
                    generation_contract={
                        "provider": "comfy-h3",
                        "model": plan["weapon_id"],
                        "version": "1",
                        "parameters": {
                            "source_endpoint": plan["source_endpoint"],
                            "audio_policy": audio_policy,
                            "mode": plan["mode"],
                            "has_last_frame": bool(
                                plan.get("mode") == "flf" and plan.get("last_path")
                            ),
                        },
                    },
                )
                queue_job_id = str(job.get("id") or "")
                # If job already succeeded (idempotent add), skip re-complete.
                if queue_job_id and job.get("status") != "succeeded":
                    claimed = mq.claim()
                    if str(claimed.get("id") or "") != queue_job_id:
                        raise H3WorkflowError(
                            f"queue claim returned unexpected job {claimed.get('id')!r}; "
                            f"expected {queue_job_id}"
                        )
                    token = str(claimed.get("claim_token") or "")
                    if not token:
                        raise H3WorkflowError("queue claim missing claim_token")
                    mq.complete(
                        job_id=queue_job_id,
                        claim_token=token,
                        endpoint=op,
                        output=deliver,
                        provider_request_id=str(result.get("prompt_id") or ""),
                    )
        except Exception as exc:  # noqa: BLE001 - queue is helpful, not required for run
            receipt["queue_error"] = str(exc)[:300]
            write_json(receipt_path, receipt)

    register_result = None
    if register:
        register_result = register_h3_clip(
            base,
            shot_id=shot_id,
            source=deliver,
            source_endpoint=str(plan["source_endpoint"]),
            status=status,
            queue_job_id=queue_job_id,
            audio_policy=audio_policy_effective,
            use_clip_audio=use_clip_audio,
            review_note=(
                f"H3 {plan['mode']} pilot; audio_policy={audio_policy} "
                f"effective={audio_policy_effective}"
            ),
        )
        receipt["register"] = register_result
        write_json(receipt_path, receipt)

    return {
        "ok": True,
        "shot_id": shot_id,
        "mode": plan["mode"],
        "weapon_id": plan["weapon_id"],
        "source_endpoint": plan["source_endpoint"],
        "raw_path": str(raw_out),
        "deliver_path": str(deliver),
        "audio_stripped": stripped,
        "audio_policy": audio_policy,
        "audio_policy_effective": audio_policy_effective,
        "use_clip_audio": use_clip_audio,
        "queue_job_id": queue_job_id,
        "receipt": str(receipt_path),
        "register": register_result,
        "command_next": (
            None
            if register
            else (
                f'aifilm register-clip --root "{base}" --shot-id {shot_id} '
                f'--source "{deliver}" --source-endpoint {plan["source_endpoint"]} '
                f"--status candidate"
            )
        ),
    }


def register_h3_clip(
    root: Path | str,
    *,
    shot_id: str,
    source: Path,
    source_endpoint: str,
    status: str = "candidate",
    queue_job_id: str | None = None,
    audio_policy: str = "prefer_native",
    use_clip_audio: bool | None = None,
    review_note: str = "H3 local plate",
) -> dict[str, Any]:
    """Register an H3 deliverable into manifest with audio policy metadata."""
    if source_endpoint not in _H3_ENDPOINTS:
        raise H3WorkflowError(f"not an H3 endpoint: {source_endpoint}")
    base = _root(root)
    source = Path(source).expanduser().resolve()
    if not source.is_file():
        raise H3WorkflowError(f"source clip missing: {source}")

    # Reuse register-clip CLI path for full gate compatibility.
    scripts = Path(__file__).resolve().parent.parent
    aifilm = scripts / "aifilm"
    cmd = [
        str(aifilm),
        "register-clip",
        "--root",
        str(base),
        "--shot-id",
        shot_id,
        "--source",
        str(source),
        "--source-endpoint",
        source_endpoint,
        "--status",
        status,
        "--review-note",
        review_note,
    ]
    if queue_job_id:
        cmd.extend(("--queue-job-id", queue_job_id))
    if status == "approved":
        cmd.extend(("--identity-approved", "--motion-approved"))
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise H3WorkflowError(f"register-clip failed: {(proc.stderr or proc.stdout or '')[:400]}")
    # Annotate manifest clip with H3 audio policy for post.
    if use_clip_audio is None:
        use_clip_audio = audio_policy not in {"strip_native_use_tts_bgm", "mute_native"}
    manifest_path = base / "manifest.json"
    manifest = read_json(manifest_path) or {}
    clips = manifest.setdefault("clips", {}) if isinstance(manifest, dict) else {}
    rec = clips.get(shot_id) if isinstance(clips, dict) else None
    if isinstance(rec, dict):
        rec["audio_policy"] = audio_policy
        rec["provider"] = "comfy-h3"
        rec["h3"] = True
        rec["use_clip_audio"] = bool(use_clip_audio)
        write_json(manifest_path, manifest)
    return {
        "ok": True,
        "shot_id": shot_id,
        "source_endpoint": source_endpoint,
        "status": status,
        "stdout": (proc.stdout or "")[:500],
        "audio_policy": audio_policy,
        "use_clip_audio": bool(use_clip_audio),
    }


def list_h3_eligible_shots(
    root: Path | str,
    *,
    include_challenge: bool = False,
    include_done: bool = False,
) -> dict[str, Any]:
    """List H3 jobs: primary restricted by default; ``include_challenge`` adds Fill-Idle P2.

    Each row includes max-effect mode (I2V/R2V/T2V) + Fill-Idle priority (P0a–P2).
    """
    from h3_fill_idle import build_fill_idle_queue

    base = _root(root)
    queue = build_fill_idle_queue(
        base,
        include_challenge=include_challenge,
        include_done=include_done,
    )
    if not queue.get("ok"):
        return {
            "schema_version": 1,
            "kind": "ai-film-h3-eligible-shots",
            "ok": False,
            "error": queue.get("error"),
            "count": 0,
            "shots": [],
            "policy": "h3_max_effect_v1+fill_idle_v1",
        }

    # Shape rows for backward-compatible consumers + new priority fields
    rows = []
    for row in queue.get("shots") or []:
        if not include_challenge and not row.get("primary_h3"):
            continue
        if not include_done and row.get("status") in {"done", "skip", "poison_blocked"}:
            # primary pending/retry only when not include_done
            if row.get("status") != "retry":
                if not row.get("command"):
                    continue
        sid = row["shot_id"]
        mode = row.get("mode") or "i2v"
        rows.append(
            {
                "shot_id": sid,
                "content_class": row.get("content_class"),
                "provider_lock": row.get("provider_lock"),
                "mode": mode,
                "mode_reasons": list(row.get("mode_reasons") or []),
                "alt_mode": row.get("alt_mode"),
                "alt_reasons": list(row.get("alt_reasons") or []),
                "weapon_id": row.get("weapon_id"),
                "recommended_weapon": row.get("weapon_id"),
                "audio_policy": None,
                "has_still": row.get("has_still"),
                "spoken_text": row.get("spoken_text"),
                "motion_tier": row.get("motion_tier"),
                "command": row.get("command")
                or f'aifilm h3 run --root "{base}" --shot-id {sid} --mode {mode} --register',
                "command_alt": row.get("command_alt"),
                # Fill-Idle
                "priority": row.get("priority"),
                "priority_rank": row.get("priority_rank"),
                "lane": row.get("lane"),
                "status": row.get("status"),
                "primary_h3": row.get("primary_h3"),
                "fill_reasons": list(row.get("reasons") or []),
                "best_mean": row.get("best_mean"),
                "below_floor": row.get("below_floor"),
                "take_count": row.get("take_count"),
                "has_h3_take": row.get("has_h3_take"),
            }
        )

    # re-sort (queue already sorted; filter may have changed)
    rows.sort(
        key=lambda r: (
            int(r.get("priority_rank") or 99),
            float(r["best_mean"])
            if r.get("priority") == "P2" and r.get("best_mean") is not None
            else 0.0,
            str(r.get("shot_id") or ""),
        )
    )
    pending = [r for r in rows if r.get("command") and r.get("status") not in {"done", "skip"}]
    return {
        "schema_version": 1,
        "kind": "ai-film-h3-eligible-shots",
        "ok": True,
        "count": len(rows),
        "pending_count": len(pending),
        "by_priority": queue.get("by_priority"),
        "next": queue.get("next") if include_challenge else (pending[0] if pending else None),
        "policy": "h3_max_effect_v1+fill_idle_v1",
        "include_challenge": include_challenge,
        "shots": rows,
        "ops_reminder": [
            "aifilm comfy free-memory --confirm  # before mode switch",
            "I2V lock face · R2V energy/mouth · T2V faceless only",
            "Fill-Idle: P0 primary → P1 weak → P2 challenge (lowest mean first)",
            "continue → endframe I2V; bulk needs pilot approve",
            "PK: aifilm h3 pk-compare then human select-shortlist --promote",
        ],
    }

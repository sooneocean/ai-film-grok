#!/usr/bin/env python3
"""End-to-end MiniMax H3 local motion lane for hybrid_h3 / comfy-h3 films.

Closes the gap between armory pilot weapons and film production:
plan → generate on 5090 → optional silent plate → queue complete → register-clip.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

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
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    chain = str(dsl.get("chain_mode") or shot.get("chain_mode") or "").strip().lower()
    if chain == "continue":
        return True
    if str(shot.get("parent_shot_id") or "").strip():
        return True
    return False


def _previous_shot_id(spec: dict[str, Any], shot_id: str, shot: dict[str, Any]) -> str | None:
    parent = str(shot.get("parent_shot_id") or "").strip()
    if parent:
        return parent
    ids = [str(s.get("id")) for s in _iter_shots(spec)]
    if shot_id not in ids:
        return None
    idx = ids.index(shot_id)
    if idx <= 0:
        return None
    return ids[idx - 1]


def resolve_continue_handoff(
    root: Path | str,
    shot_id: str,
    *,
    shot: dict[str, Any] | None = None,
    spec: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Phase C · Read previous-shot continue handoff (endframe + DF packet).

    Never overwrites approved stills. Optional copy into stills/ only when
    the still is missing AND ``AIFILM_CONTINUE_COPY_STILL=1``.
    """
    base = _root(root)
    if not isinstance(spec, dict):
        try:
            spec = _load_spec(base)
        except H3WorkflowError:
            spec = {}
    if not isinstance(shot, dict):
        try:
            shot = _find_shot(spec, shot_id) if spec else {}
        except H3WorkflowError:
            shot = {}
    prev_id = _previous_shot_id(spec or {}, shot_id, shot or {})
    out: dict[str, Any] = {
        "schema_version": 1,
        "kind": "h3-continue-handoff-resolve",
        "shot_id": shot_id,
        "prev_shot_id": prev_id,
        "wants_continue": _shot_wants_continue(shot or {}),
        "ok": False,
        "end_frame": None,
        "handoff_meta": None,
        "copied_to_stills": False,
        "still_dest": None,
    }
    if not prev_id:
        out["note"] = "no previous/parent shot for continue handoff"
        return out
    handoff_dir = base / "receipts" / "continue-handoff"
    meta_path = handoff_dir / f"{prev_id}.json"
    end_png = handoff_dir / f"{prev_id}_end.png"
    meta = read_json(meta_path) if meta_path.is_file() else {}
    if isinstance(meta, dict) and meta:
        out["handoff_meta"] = {
            k: meta.get(k)
            for k in (
                "shot_id",
                "mode",
                "dramatic_function",
                "heat_phase",
                "core",
                "ok",
                "end_frame",
            )
        }
        ef = meta.get("end_frame")
        if ef and Path(str(ef)).is_file():
            end_png = Path(str(ef))
    if not end_png.is_file():
        out["note"] = f"missing continue end frame for prev={prev_id}"
        return out
    out["end_frame"] = str(end_png)
    out["ok"] = True
    # Optional: fill empty stills/ slot only (never overwrite approved)
    copy_on = os.environ.get("AIFILM_CONTINUE_COPY_STILL", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    still_dest = base / "stills" / f"{shot_id}.png"
    out["still_dest"] = str(still_dest)
    if copy_on and not still_dest.is_file():
        try:
            still_dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(end_png, still_dest)
            out["copied_to_stills"] = True
        except OSError as exc:
            out["copy_error"] = str(exc)[:160]
    elif still_dest.is_file():
        out["note"] = "approved/existing still present — not overwritten by handoff"
    return out


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


def plan_h3_shot(root: Path | str, shot_id: str) -> dict[str, Any]:
    """Return a machine-readable H3 execution plan for one shot."""
    base = _root(root)
    spec = _load_spec(base)
    shot = _find_shot(spec, shot_id)
    intent = build_shot_intent(spec, shot)
    h3 = spec.get("h3") if isinstance(spec.get("h3"), dict) else {}
    # Surface motion-core fields on plan for receipts / agent routing.
    plan_core = {
        "dramatic_function": intent.get("dramatic_function"),
        "want_beat": intent.get("want_beat"),
        "motion_tier": intent.get("motion_tier"),
        "spoken_text": intent.get("spoken_text"),
        "has_action_core": intent.get("has_action_core"),
    }
    mode = "i2v"
    op = str(intent.get("operation") or "image_to_video")
    if op == "text_to_video":
        mode = "t2v"
    if str(shot.get("h3_mode") or "").strip().lower() in {"t2v", "i2v", "r2v"}:
        mode = str(shot.get("h3_mode")).strip().lower()
    elif str(shot.get("operation") or "").strip().lower() in {
        "reference_to_video",
        "reference-to-video",
        "r2v",
    }:
        mode = "r2v"
    weapon = {
        "t2v": "minimax-h3-t2v-pilot",
        "i2v": "minimax-h3-i2v-pilot",
        "r2v": "minimax-h3-r2v-pilot",
    }[mode]
    endpoint = {
        "t2v": "local_minimax_h3_t2v",
        "i2v": "local_minimax_h3_i2v",
        "r2v": "local_minimax_h3_r2v",
    }[mode]
    approved = _approved_still(base, shot_id)
    cont = resolve_continue_handoff(base, shot_id, shot=shot, spec=spec)
    still: Path | None = approved
    still_source: str | None = "approved" if approved else None
    # Phase C: chain_mode=continue → prefer previous endframe; never clobber approved file on disk
    if cont.get("ok") and cont.get("end_frame"):
        end_p = Path(str(cont["end_frame"]))
        if end_p.is_file():
            if cont.get("wants_continue"):
                still = end_p
                still_source = "continue_handoff"
            elif approved is None:
                still = end_p
                still_source = "continue_handoff_fallback"
            # If approved exists and not continue: keep approved (identity lock)
    # After optional env copy, re-check stills/ for empty-slot fill
    if still is None:
        filled = base / "stills" / f"{shot_id}.png"
        if filled.is_file():
            still = filled
            still_source = "stills_after_continue_copy"
    audio_policy = str(intent.get("audio_policy") or h3.get("audio_policy") or "prefer_native")
    max_dur = float(intent.get("max_duration_sec") or h3.get("max_duration_sec") or 8)
    enabled = bool(intent.get("h3_enabled") or h3.get("enabled") is True)
    return {
        "schema_version": 1,
        "kind": "ai-film-h3-shot-plan",
        "ok": True,
        "shot_id": shot_id,
        "mode": mode,
        "weapon_id": weapon,
        "source_endpoint": endpoint,
        "provider": "comfy-h3",
        "intent": intent,
        "motion_core": plan_core,
        "h3_enabled": enabled,
        "still_path": str(still) if still else None,
        "still_source": still_source,
        "continue_handoff": cont,
        "requires_still": mode in {"i2v", "r2v"},
        "audio_policy": audio_policy,
        "max_duration_sec": max_dur,
        "megapixels_draft": float(h3.get("megapixels_draft") or 0.2),
        "allow_bulk": bool(h3.get("allow_bulk")),
        "command": (f'aifilm h3 run --root "{base}" --shot-id {shot_id} --mode {mode} --register'),
    }


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
    """Extract end frame + dramatic packet for next-shot I2V continue (P2)."""
    from motion_prompt_spine import core_fields, dramatic_function_of, heat_phase_of

    handoff_dir = root / "receipts" / "continue-handoff"
    handoff_dir.mkdir(parents=True, exist_ok=True)
    end_png = handoff_dir / f"{shot_id}_end.png"
    meta: dict[str, Any] = {
        "schema_version": 1,
        "kind": "h3-continue-handoff",
        "shot_id": shot_id,
        "mode": mode,
        "seed": seed,
        "source_clip": str(deliver),
        "end_frame": None,
        "dramatic_function": dramatic_function_of(shot) or None,
        "heat_phase": heat_phase_of(shot) or None,
        "core": core_fields(None, shot),
        "ok": False,
    }
    if not deliver.is_file():
        write_json(handoff_dir / f"{shot_id}.json", meta)
        return meta
    try:
        proc = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-sseof",
                "-0.12",
                "-i",
                str(deliver),
                "-frames:v",
                "1",
                "-q:v",
                "2",
                str(end_png),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode == 0 and end_png.is_file():
            meta["end_frame"] = str(end_png)
            meta["ok"] = True
            # Read side: plan_h3_shot / resolve_continue_handoff (no silent stills overwrite)
            meta["note"] = (
                f"Next shot chain_mode=continue → plan uses {end_png} automatically; "
                f"optional AIFILM_CONTINUE_COPY_STILL=1 copies only if stills/<next>.png missing"
            )
    except Exception as exc:  # noqa: BLE001
        meta["error"] = str(exc)[:200]
    write_json(handoff_dir / f"{shot_id}.json", meta)
    return meta


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
) -> dict[str, Any]:
    """Generate one H3 clip for a film shot and optionally register it."""
    base = _root(root)
    plan = plan_h3_shot(base, shot_id)
    # Film-lane default: production when weapon is promoted; experimental only if needed.
    stage = (production_stage or "production").strip().lower()
    if allow_experimental is None:
        allow_experimental = stage == "pilot"
    if mode:
        mode_norm = mode.strip().lower()
        if mode_norm not in {"t2v", "i2v", "r2v"}:
            raise H3WorkflowError("mode must be t2v, i2v, or r2v")
        plan["mode"] = mode_norm
        plan["weapon_id"] = {
            "t2v": "minimax-h3-t2v-pilot",
            "i2v": "minimax-h3-i2v-pilot",
            "r2v": "minimax-h3-r2v-pilot",
        }[mode_norm]
        plan["source_endpoint"] = {
            "t2v": "local_minimax_h3_t2v",
            "i2v": "local_minimax_h3_i2v",
            "r2v": "local_minimax_h3_r2v",
        }[mode_norm]
        plan["requires_still"] = mode_norm in {"i2v", "r2v"}

    if plan["requires_still"] and not plan.get("still_path"):
        raise H3WorkflowError(
            f"H3 {plan['mode']} requires an approved still/keyframe for {shot_id}"
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
    # Persist assembled spine for audit / Grok parity review.
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
    # T2V still needs a path object; provider only uploads for i2v/r2v.
    result = provider.generate(
        keyframe=keyframe,
        prompt=prompt,
        out=raw_out,
        mode=plan["mode"],
        seed=seed,
        timeout_sec=timeout_sec,
        allow_experimental=bool(allow_experimental),
        production_stage=stage,
        filename_prefix=f"aifilm/h3/{shot_id}",
    )
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
    }
    receipt_path = base / "receipts" / f"h3-run-{shot_id}.json"
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
                job = mq.add_job(
                    shot_id=shot_id,
                    operation=op,
                    prompt_file=prompt_file,
                    inputs=[Path(plan["still_path"])],
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
    scripts = Path(__file__).resolve().parent
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


def list_h3_eligible_shots(root: Path | str) -> dict[str, Any]:
    """List shots that hybrid/H3 intent would send to local MiniMax."""
    base = _root(root)
    spec = _load_spec(base)
    rows = []
    for shot in _iter_shots(spec):
        intent = build_shot_intent(spec, shot)
        if (
            intent.get("recommended_provider") == "comfy-h3"
            or intent.get("provider_lock") == "comfy-h3"
        ):
            rows.append(
                {
                    "shot_id": shot.get("id"),
                    "content_class": intent.get("content_class"),
                    "provider_lock": intent.get("provider_lock"),
                    "recommended_weapon": intent.get("recommended_weapon"),
                    "audio_policy": intent.get("audio_policy"),
                }
            )
    return {
        "schema_version": 1,
        "kind": "ai-film-h3-eligible-shots",
        "ok": True,
        "count": len(rows),
        "shots": rows,
    }

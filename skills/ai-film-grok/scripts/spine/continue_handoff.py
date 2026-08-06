#!/usr/bin/env python3
"""Continue handoff — endframe + DF packet for next-shot I2V (H3 + Grok shared).

Write: after a clip lands (H3 run, media-queue complete, register-clip).
Read: plan_h3_shot / prompt_injector I2V when chain_mode=continue.

Never overwrites approved stills/. Optional copy only if missing +
AIFILM_CONTINUE_COPY_STILL=1.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from util import read_json, write_json


def _root(path: Path | str) -> Path:
    return Path(path).expanduser().resolve()


def shot_wants_continue(shot: dict[str, Any]) -> bool:
    """True when this shot is an endframe-continue link."""
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    chain = str(dsl.get("chain_mode") or shot.get("chain_mode") or "").strip().lower()
    if chain == "continue":
        return True
    if str(shot.get("parent_shot_id") or "").strip():
        return True
    return False


def iter_shot_ids(spec: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    for scene in spec.get("scenes") or []:
        if not isinstance(scene, dict):
            continue
        for shot in scene.get("shots") or []:
            if isinstance(shot, dict) and shot.get("id"):
                ids.append(str(shot["id"]))
    if not ids and isinstance(spec.get("shots"), list):
        for shot in spec["shots"]:
            if isinstance(shot, dict) and shot.get("id"):
                ids.append(str(shot["id"]))
    return ids


def find_shot(spec: dict[str, Any], shot_id: str) -> dict[str, Any] | None:
    for scene in spec.get("scenes") or []:
        if not isinstance(scene, dict):
            continue
        for shot in scene.get("shots") or []:
            if isinstance(shot, dict) and str(shot.get("id")) == shot_id:
                return shot
    if isinstance(spec.get("shots"), list):
        for shot in spec["shots"]:
            if isinstance(shot, dict) and str(shot.get("id")) == shot_id:
                return shot
    return None


def previous_shot_id(
    spec: dict[str, Any], shot_id: str, shot: dict[str, Any] | None = None
) -> str | None:
    sh = shot if isinstance(shot, dict) else find_shot(spec, shot_id) or {}
    parent = str(sh.get("parent_shot_id") or "").strip()
    if parent:
        return parent
    ids = iter_shot_ids(spec)
    if shot_id not in ids:
        return None
    idx = ids.index(shot_id)
    if idx <= 0:
        return None
    return ids[idx - 1]


def write_continue_handoff(
    root: Path | str,
    *,
    shot_id: str,
    deliver: Path | str,
    shot: dict[str, Any] | None = None,
    mode: str = "i2v",
    engine: str = "grok",
    seed: int | None = None,
    spec: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Extract end frame + dramatic packet for next-shot I2V continue."""
    from motion_prompt_spine import core_fields, dramatic_function_of, heat_phase_of

    base = _root(root)
    deliver_p = Path(deliver).expanduser().resolve()
    shot_d = shot if isinstance(shot, dict) else {}
    if not shot_d and isinstance(spec, dict):
        shot_d = find_shot(spec, shot_id) or {}

    handoff_dir = base / "receipts" / "continue-handoff"
    handoff_dir.mkdir(parents=True, exist_ok=True)
    end_png = handoff_dir / f"{shot_id}_end.png"
    meta: dict[str, Any] = {
        "schema_version": 1,
        "kind": "continue-handoff",
        "shot_id": shot_id,
        "mode": mode,
        "engine": engine,
        "seed": seed,
        "source_clip": str(deliver_p) if deliver_p else None,
        "end_frame": None,
        "dramatic_function": dramatic_function_of(shot_d) or None if shot_d else None,
        "heat_phase": heat_phase_of(shot_d) or None if shot_d else None,
        "core": core_fields(spec, shot_d) if shot_d else None,
        "ok": False,
    }
    if not deliver_p.is_file():
        write_json(handoff_dir / f"{shot_id}.json", meta)
        return meta
    try:
        # Use -0.20 offset to avoid encoding tail dirty-frames (last ~0.1-0.15s often
        # suffers from H.264 compression convergence artifacts in H3 output).
        # If the frame is too blurry (Laplacian variance < threshold), fall back to -0.30.
        _SSEOF_PRIMARY = "-0.20"
        _SSEOF_FALLBACK = "-0.30"

        def _extract_end_frame(sseof: str, dest: Path) -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-sseof",
                    sseof,
                    "-i",
                    str(deliver_p),
                    "-frames:v",
                    "1",
                    "-q:v",
                    "2",
                    str(dest),
                ],
                capture_output=True,
                text=True,
                check=False,
                timeout=60,
            )

        proc = _extract_end_frame(_SSEOF_PRIMARY, end_png)
        used_sseof = _SSEOF_PRIMARY

        # Quality gate: check frame sharpness via Laplacian variance (proxy for blur).
        # Fall back to -0.30 when the primary frame is too blurry (< 40 variance units).
        if proc.returncode == 0 and end_png.is_file():
            try:
                _MIN_SHARPNESS_VARIANCE = 40.0
                _is_sharp = True
                try:
                    # Lightweight sharpness probe: read PNG and compute simple pixel variance.
                    # If numpy available use it; otherwise skip quality gate (conservative pass).
                    import numpy as np
                    from PIL import Image  # type: ignore[import]

                    img = np.array(Image.open(end_png).convert("L"), dtype=float)
                    # Laplacian kernel approximate variance: std of second derivative
                    laplacian = np.array([[0, 1, 0], [1, -4, 1], [0, 1, 0]])
                    from numpy.lib.stride_tricks import sliding_window_view  # type: ignore[import]
                    h, w = img.shape
                    if h > 2 and w > 2:
                        padded = np.pad(img, 1, mode="reflect")
                        patches = sliding_window_view(padded, (3, 3))
                        lap_vals = (patches * laplacian).sum(axis=(-2, -1))
                        variance = float(lap_vals.var())
                        _is_sharp = variance >= _MIN_SHARPNESS_VARIANCE
                except Exception:  # noqa: BLE001
                    pass  # skip quality gate when deps unavailable

                if not _is_sharp:
                    fallback_png = handoff_dir / f"{shot_id}_end_fallback.png"
                    proc2 = _extract_end_frame(_SSEOF_FALLBACK, fallback_png)
                    if proc2.returncode == 0 and fallback_png.is_file():
                        # Use fallback; rename it to canonical end_png
                        fallback_png.replace(end_png)
                        used_sseof = _SSEOF_FALLBACK
            except Exception:  # noqa: BLE001
                pass  # never let quality gate block the handoff

        if proc.returncode == 0 and end_png.is_file():
            meta["end_frame"] = str(end_png)
            meta["ok"] = True
            meta["sseof_used"] = used_sseof
            meta["note"] = (
                f"Next shot chain_mode=continue → plan uses {end_png}; "
                f"AIFILM_CONTINUE_COPY_STILL=1 copies only if stills/<next>.png missing"
            )
    except Exception as exc:  # noqa: BLE001
        meta["error"] = str(exc)[:200]
    write_json(handoff_dir / f"{shot_id}.json", meta)
    return meta


def resolve_continue_handoff(
    root: Path | str,
    shot_id: str,
    *,
    shot: dict[str, Any] | None = None,
    spec: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Read previous-shot continue handoff (endframe + DF packet)."""
    base = _root(root)
    if not isinstance(spec, dict):
        spec = read_json(base / "film-spec.json") or {}
    if not isinstance(spec, dict):
        spec = {}
    if not isinstance(shot, dict):
        shot = find_shot(spec, shot_id) or {}
    prev_id = previous_shot_id(spec, shot_id, shot)
    out: dict[str, Any] = {
        "schema_version": 1,
        "kind": "continue-handoff-resolve",
        "shot_id": shot_id,
        "prev_shot_id": prev_id,
        "wants_continue": shot_wants_continue(shot or {}),
        "ok": False,
        "end_frame": None,
        "handoff_meta": None,
        "copied_to_stills": False,
        "still_dest": None,
        "prompt_clause": None,
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
                "engine",
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
    out["prompt_clause"] = (
        "CONTINUE from previous end frame: preserve identity, wardrobe, body pose, "
        "and spatial continuity; animate forward from this exact last frame — "
        "do not reset to a new start pose or re-dress."
    )
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


def maybe_write_for_clip(
    root: Path | str,
    shot_id: str,
    clip_path: Path | str,
    *,
    engine: str = "grok",
    mode: str = "i2v",
) -> dict[str, Any] | None:
    """Best-effort write after Grok/H3 clip lands (never raises)."""
    try:
        base = _root(root)
        spec = read_json(base / "film-spec.json") or {}
        shot = find_shot(spec if isinstance(spec, dict) else {}, shot_id) or {}
        return write_continue_handoff(
            base,
            shot_id=shot_id,
            deliver=clip_path,
            shot=shot,
            mode=mode,
            engine=engine,
            spec=spec if isinstance(spec, dict) else None,
        )
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)[:160], "shot_id": shot_id}

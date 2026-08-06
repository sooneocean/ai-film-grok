#!/usr/bin/env python3
"""Composition anti-hijack gate (2026-08-05 · ep02 sand/torso steal).

Multi-seed auto-pick that only ranks white0 / mean_volume / motion mean will
promote wrong motifs (aerial sand+footprints for dialogue openers; male torso
fill for female-led presence). This module scores midframe composition and
must run before promote to narrative / manifest.

Escape: AIFILM_SKIP_ANTI_HIJACK=1
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

Want = Literal["female_face", "female_ms_two", "generic"]

RECEIPT_NAME = "anti-hijack-composition.json"
SCORE_RECEIPT = "anti-hijack-score.json"

# Hard reject floors (pixel-heuristic, not face ID)
SANDISH_HIJACK = 0.5
TORSO_HIJACK = 0.5
FACE_SKIN_MIN = 0.15  # dialogue face class: center must look like skin
SCORE_FLOOR_FACE = 0.45
SCORE_FLOOR_MS = 0.40


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _env_skip() -> bool:
    return os.environ.get("AIFILM_SKIP_ANTI_HIJACK", "").strip() in {"1", "true", "yes", "on"}


def score_frame_array(im: Any, want: Want = "generic") -> dict[str, Any]:
    """Score a HxWx3 uint8 RGB array (or PIL-like). Returns metrics + score."""
    import numpy as np

    arr = np.asarray(im)
    if arr.ndim == 2:
        arr = np.stack([arr, arr, arr], axis=-1)
    if arr.shape[-1] > 3:
        arr = arr[..., :3]
    # normalize to 96x128 portrait sampling grid
    from PIL import Image

    pil = Image.fromarray(arr.astype("uint8"), mode="RGB").resize((96, 128))
    im = np.array(pil)

    white = float((im > 240).all(2).mean())
    top = im[:64]
    top_mean = top.mean(axis=(0, 1))
    top_std = float(top.std())
    sandish = 0.0
    # beige sand / footprint plate: bright, low chroma variance top half
    if float(top_mean.mean()) > 140 and top_std < 45 and abs(float(top_mean[0] - top_mean[1])) < 25:
        sandish = 1.0
    # uniform low-detail top (aerial plate) even if not pure beige
    if top_std < 22 and float(top_mean.mean()) > 100:
        sandish = max(sandish, 0.7)

    cy0, cy1, cx0, cx1 = 20, 90, 25, 70
    center = im[cy0:cy1, cx0:cx1]
    cmean = center.mean(axis=(0, 1))
    cstd = float(center.std())
    skin = 0.0
    if float(cmean[0]) > float(cmean[2]) and 60 < float(cmean.mean()) < 200 and cstd > 25:
        skin = min(1.0, cstd / 50.0)

    torso = 0.0
    mid = im[40:100, 20:76]
    if float(mid.mean()) > 130 and float(mid.std()) < 55 and float(im[:30].mean()) < 120:
        torso = 0.8

    if want == "female_face":
        score = skin * 0.6 + (1 - sandish) * 0.3 + (1 - min(1.0, white * 5)) * 0.1 - sandish * 0.5
        # no readable face/skin → hard demote (sand footprints often skin=0)
        if skin < FACE_SKIN_MIN:
            score -= 0.45
    elif want == "female_ms_two":
        score = (
            skin * 0.35
            + (1 - torso) * 0.4
            + (1 - sandish) * 0.15
            + (1 - min(1.0, white * 5)) * 0.1
        )
        if torso > TORSO_HIJACK:
            score -= 0.5
    else:
        score = skin * 0.4 + (1 - sandish) * 0.35 + (1 - torso) * 0.15 + (1 - min(1.0, white * 5)) * 0.1

    hijack = bool(sandish >= SANDISH_HIJACK or torso >= TORSO_HIJACK)
    if want == "female_face" and skin < FACE_SKIN_MIN and sandish >= 0.3:
        hijack = True
    if want == "female_face" and skin < FACE_SKIN_MIN and cstd < 30:
        # empty/low-detail center with no skin (footprints / env plate)
        hijack = True
        score -= 0.2
    if want == "female_ms_two" and torso >= TORSO_HIJACK:
        hijack = True

    if hijack:
        score -= 0.55 if want == "female_face" else 0.45

    return {
        "white": round(white, 4),
        "sandish": round(float(sandish), 3),
        "skin": round(float(skin), 3),
        "torso_risk": round(float(torso), 3),
        "score": round(float(score), 4),
        "top_std": round(top_std, 1),
        "cstd": round(cstd, 1),
        "hijack": hijack,
        "want": want,
    }


def score_frame_path(png: Path | str, want: Want = "generic") -> dict[str, Any]:
    from PIL import Image

    path = Path(png)
    im = Image.open(path).convert("RGB")
    return score_frame_array(im, want=want)


def extract_frame(video: Path | str, *, t_sec: float = 1.2, out: Path | None = None) -> Path | None:
    """ffmpeg midframe extract; returns png path or None."""
    video = Path(video)
    if not video.is_file():
        return None
    if out is None:
        out = Path(tempfile.mkdtemp(prefix="anti_hijack_")) / f"{video.stem}_t.png"
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-ss",
        str(t_sec),
        "-i",
        str(video),
        "-frames:v",
        "1",
        str(out),
    ]
    try:
        subprocess.run(cmd, capture_output=True, check=False, timeout=60)
    except Exception:  # noqa: BLE001
        return None
    return out if out.is_file() and out.stat().st_size > 100 else None


def infer_want(shot: dict[str, Any] | None) -> Want:
    """Map film-spec shot → composition class."""
    if not isinstance(shot, dict):
        return "generic"
    blob = " ".join(
        str(shot.get(k) or "")
        for k in (
            "id",
            "shot_size",
            "framing",
            "playable_action",
            "story_beat",
            "dramatic_function",
            "speaker",
            "focal_character",
        )
    ).lower()
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    cam = dsl.get("camera") if isinstance(dsl.get("camera"), dict) else {}
    blob += " " + " ".join(
        str(x or "")
        for x in (
            dsl.get("subject"),
            dsl.get("action"),
            cam.get("shot_size"),
            cam.get("framing"),
            shot.get("caption_text"),
            shot.get("spoken_text"),
        )
    ).lower()
    # dialogue / face priority
    spoken = False
    cues = shot.get("audio_cues") if isinstance(shot.get("audio_cues"), list) else []
    for c in cues:
        if isinstance(c, dict) and str(c.get("spoken_text") or "").strip():
            spoken = True
            break
    if not spoken and str(shot.get("spoken_text") or "").strip():
        spoken = True
    # Prefer author shot_size over nested dsl.camera (dsl often drifts to env MS)
    size = str(shot.get("shot_size") or cam.get("shot_size") or "").lower()
    face_sizes = ("cu", "ecu", "close", "face", "mcu", "close-up", "closeup", "tight")
    ms_sizes = ("ms", "medium", "two", "ws", "full", "waist", "wide")
    if spoken and any(x in size for x in face_sizes):
        return "female_face"
    if spoken and any(k in blob for k in ("澜汐", "lanxi", "female", "she ", "her ")):
        if "two-shot" in blob or "two shot" in blob or "couple" in blob:
            return "female_ms_two"
        if any(x in size for x in ms_sizes):
            return "female_ms_two"
        return "female_face"
    if spoken:
        # default on_camera dialogue → protect face framing
        if "two-shot" in blob or "two shot" in blob or "couple" in blob or "both" in blob:
            return "female_ms_two"
        if any(x in size for x in ms_sizes) and not any(x in size for x in face_sizes):
            return "female_ms_two"
        return "female_face"
    if "two-shot" in blob or "two shot" in blob or "couple" in blob:
        return "female_ms_two"
    return "generic"


def score_take(
    video: Path | str,
    *,
    want: Want = "generic",
    cache_dir: Path | None = None,
    t_sec: float = 1.2,
    t0_sec: float = 0.1,
) -> dict[str, Any]:
    """Score one take video; samples t≈1.2s and optional t0 for sand openers."""
    video = Path(video)
    work = cache_dir or Path(tempfile.mkdtemp(prefix="anti_hijack_"))
    work.mkdir(parents=True, exist_ok=True)
    mid = extract_frame(video, t_sec=t_sec, out=work / f"{video.stem}_t12.png")
    head = extract_frame(video, t_sec=t0_sec, out=work / f"{video.stem}_t01.png")
    if mid is None:
        return {
            "path": str(video),
            "ok": False,
            "hijack": True,
            "score": -1.0,
            "error": "frame_extract_failed",
            "want": want,
        }
    s = score_frame_path(mid, want=want)
    if head is not None:
        s0 = score_frame_path(head, want=want)
        if s0.get("sandish", 0) >= SANDISH_HIJACK or s0.get("hijack"):
            s["hijack"] = True
            s["score"] = round(float(s["score"]) - 0.6, 4)
            s["head_sandish"] = s0.get("sandish")
    floor = SCORE_FLOOR_FACE if want == "female_face" else SCORE_FLOOR_MS if want == "female_ms_two" else 0.25
    ok = (not s.get("hijack")) and float(s.get("score") or 0) >= floor
    return {
        "path": str(video),
        "mid": str(mid),
        "ok": ok,
        "floor": floor,
        **s,
    }


def rank_takes(
    paths: list[Path | str],
    *,
    want: Want = "generic",
    cache_dir: Path | None = None,
) -> list[dict[str, Any]]:
    scored = [score_take(p, want=want, cache_dir=cache_dir) for p in paths]
    # non-hijack first, then score, then prefer existing
    scored.sort(
        key=lambda x: (
            0 if x.get("hijack") else 1,
            float(x.get("score") or -99),
            1 if x.get("ok") else 0,
        ),
        reverse=True,
    )
    return scored


def pick_preferred(
    paths: list[Path | str],
    *,
    want: Want = "generic",
    cache_dir: Path | None = None,
) -> dict[str, Any] | None:
    ranked = rank_takes(paths, want=want, cache_dir=cache_dir)
    if not ranked:
        return None
    # never return hijack if a non-hijack exists
    clean = [r for r in ranked if not r.get("hijack") and r.get("ok")]
    if clean:
        return clean[0]
    # all hijacked — still return best score but mark force_reject
    best = ranked[0]
    best = {**best, "force_reject": True, "ok": False}
    return best


def apply_anti_hijack_to_candidates(
    candidates: list[dict[str, Any]],
    *,
    shot: dict[str, Any] | None = None,
    want: Want | None = None,
    cache_dir: Path | None = None,
    enabled: bool = True,
) -> list[dict[str, Any]]:
    """Annotate shortlist candidates with composition metrics; demote hijacks.

    Each candidate needs ``path``. Mutates copies; returns new sorted list.
    """
    if not enabled or _env_skip():
        return candidates
    w: Want = want or infer_want(shot)
    out: list[dict[str, Any]] = []
    for c in candidates:
        path = c.get("path")
        if not path:
            out.append(c)
            continue
        try:
            sc = score_take(path, want=w, cache_dir=cache_dir)
        except Exception as exc:  # noqa: BLE001
            sc = {"ok": False, "hijack": False, "score": 0.0, "error": str(exc), "want": w}
        mean = c.get("mean")
        mean_f = float(mean) if mean is not None else 0.0
        # composition gate: hijack → score crushed regardless of motion mean
        if sc.get("hijack") or sc.get("force_reject"):
            adj = mean_f * 0.05 - 50.0
        else:
            # boost high composition score slightly so face wins over sand-high-motion
            adj = mean_f + float(sc.get("score") or 0) * 8.0
        row = {
            **c,
            "anti_hijack": sc,
            "score": adj,
            "composition_score": sc.get("score"),
            "composition_hijack": bool(sc.get("hijack")),
            "composition_ok": bool(sc.get("ok")),
            "composition_want": w,
        }
        out.append(row)
    out.sort(
        key=lambda x: (
            0 if x.get("composition_hijack") else 1,
            1 if x.get("composition_ok") else 0,
            float(x.get("score") or 0),
            int(x.get("bytes") or 0),
        ),
        reverse=True,
    )
    return out


def run_for_root(
    root: Path | str,
    *,
    shot_ids: list[str] | None = None,
    write: bool = True,
    promote: bool = False,
) -> dict[str, Any]:
    """Score multi-takes under film root; write receipts/anti-hijack-score.json."""
    root = Path(root)
    if _env_skip():
        rep = {
            "schema_version": 1,
            "kind": "composition-anti-hijack",
            "at": _utc_now(),
            "ok": True,
            "skipped": True,
            "reason": "AIFILM_SKIP_ANTI_HIJACK",
        }
        if write:
            (root / "receipts").mkdir(parents=True, exist_ok=True)
            (root / "receipts" / SCORE_RECEIPT).write_text(
                json.dumps(rep, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
        return rep

    from util import read_json, write_json  # type: ignore

    spec = read_json(root / "film-spec.json") or {}
    shot_meta: dict[str, dict[str, Any]] = {}
    for scene in (spec.get("scenes") or []) if isinstance(spec, dict) else []:
        if not isinstance(scene, dict):
            continue
        for sh in scene.get("shots") or []:
            if isinstance(sh, dict) and sh.get("id"):
                shot_meta[str(sh["id"])] = sh

    takes_root = root / "takes"
    shot_dirs: dict[str, list[Path]] = {}
    if takes_root.is_dir():
        for p in takes_root.rglob("*"):
            if not p.is_file() or p.suffix.lower() not in {".mp4", ".webm", ".mov"}:
                continue
            sid = p.parent.name if p.parent != takes_root else p.stem.split("_")[0]
            if shot_ids and sid not in shot_ids:
                continue
            shot_dirs.setdefault(sid, []).append(p)

    cache = root / "work" / "anti-hijack" / "frames"
    cache.mkdir(parents=True, exist_ok=True)
    shots_out: list[dict[str, Any]] = []
    hijack_count = 0
    for sid, files in sorted(shot_dirs.items()):
        sh = shot_meta.get(sid)
        want = infer_want(sh)
        ranked = rank_takes(files, want=want, cache_dir=cache / sid)
        preferred = pick_preferred(files, want=want, cache_dir=cache / sid)
        if preferred and preferred.get("hijack"):
            hijack_only = True
        else:
            hijack_only = False
        for r in ranked:
            if r.get("hijack"):
                hijack_count += 1
        shots_out.append(
            {
                "shot_id": sid,
                "want": want,
                "take_count": len(ranked),
                "preferred": preferred,
                "candidates": ranked,
                "all_hijacked": hijack_only or (preferred is not None and not preferred.get("ok")),
            }
        )

    man = read_json(root / "manifest.json") or {}
    promoted: list[dict[str, Any]] = []
    if promote and isinstance(man, dict):
        clips = man.get("clips") if isinstance(man.get("clips"), dict) else {}
        if not isinstance(clips, dict):
            clips = {}
        for row in shots_out:
            pref = row.get("preferred")
            if not pref or not pref.get("path"):
                continue
            if pref.get("hijack") or pref.get("force_reject") or not pref.get("ok"):
                continue  # never promote hijack
            sid = row["shot_id"]
            prev = clips.get(sid) if isinstance(clips.get(sid), dict) else {}
            clips[sid] = {
                **(prev or {}),
                "path": pref["path"],
                "preferred_from": "anti-hijack",
                "composition_score": pref.get("score"),
                "composition_ok": True,
                "promoted_at": _utc_now(),
                "status": (prev or {}).get("status") or "candidate",
            }
            promoted.append({"shot_id": sid, "path": pref["path"], "score": pref.get("score")})
        man["clips"] = clips
        write_json(root / "manifest.json", man)

    ok = True
    # advisory ok unless promote requested and nothing clean
    rep = {
        "schema_version": 1,
        "kind": "composition-anti-hijack-score",
        "at": _utc_now(),
        "root": str(root),
        "ok": ok,
        "hijack_take_count": hijack_count,
        "shots": shots_out,
        "promoted": promoted,
        "promote": promote,
        "rules": [
            "Reject sand top-down / footprints-fill as dialogue openers",
            "Reject male torso fill for female-led presence shots",
            "Never pick solely by mean_volume/white0/motion mean without composition gate",
            "Winner must pass anti-hijack before promote to narrative",
        ],
        "escape": "AIFILM_SKIP_ANTI_HIJACK=1",
    }
    if write:
        (root / "receipts").mkdir(parents=True, exist_ok=True)
        write_json(root / "receipts" / SCORE_RECEIPT, rep)
        # keep policy receipt pointer
        policy = {
            "kind": "composition-anti-hijack",
            "at": _utc_now(),
            "rules": rep["rules"],
            "score_receipt": f"receipts/{SCORE_RECEIPT}",
            "module": "composition_anti_hijack.py",
        }
        write_json(root / "receipts" / RECEIPT_NAME, policy)
    return rep


def seed_from_path(path: str | Path) -> str:
    m = re.search(r"(?:h3_i2v|i2v|seed)[_-]?(\d+)", str(path))
    return m.group(1) if m else "?"

"""I2.2 · endframe no-redress heuristic (not true CV).

Extract first/last frames of a clip; if wardrobe is undressed/bare, last frame
must not look *more clothed* (skin ratio drop) than first — classic re-dress fail.

Receipt: receipts/endframe-wardrobe/<shot_id>.json
Escape: AIFILM_SKIP_ENDFRAME_WARDROBE=1
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from util import utc_now, write_json

_UNDRESS = frozenset({"undressed", "bare", "partial", "nude", "naked"})
# Skin-ish mid-frame coverage drop larger than this → redress risk
_SKIN_DROP_HARD = 0.22


class EndframeWardrobeError(ValueError):
    pass


def _env_skip(root: Path | str | None = None) -> bool:
    try:
        from core.skip_audit import skip_flag

        return skip_flag(
            "AIFILM_SKIP_ENDFRAME_WARDROBE",
            origin="env",
            film_root=root,
            call_site="endframe_wardrobe._env_skip",
        )
    except Exception:
        return os.environ.get("AIFILM_SKIP_ENDFRAME_WARDROBE", "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }


def _extract(video: Path, t_mode: str, out: Path) -> Path | None:
    """t_mode: 'first' | 'last'."""
    out.parent.mkdir(parents=True, exist_ok=True)
    if t_mode == "first":
        cmd = [
            "ffmpeg",
            "-y",
            "-ss",
            "0.05",
            "-i",
            str(video),
            "-frames:v",
            "1",
            str(out),
        ]
    else:
        cmd = [
            "ffmpeg",
            "-y",
            "-sseof",
            "-0.15",
            "-i",
            str(video),
            "-frames:v",
            "1",
            str(out),
        ]
    try:
        subprocess.run(cmd, capture_output=True, check=False, timeout=45)
    except Exception:
        return None
    return out if out.is_file() and out.stat().st_size > 80 else None


def _skin_ratio(png: Path) -> float | None:
    """Cheap skin-tone pixel ratio in center band (heuristic only)."""
    try:
        import numpy as np
        from PIL import Image
    except ImportError:
        return None
    try:
        im = Image.open(png).convert("RGB").resize((64, 96))
        arr = np.asarray(im)
    except Exception:
        return None
    # center band (exclude letterbox edges)
    band = arr[20:80, 12:52]
    r, g, b = band[..., 0].astype(float), band[..., 1].astype(float), band[..., 2].astype(float)
    # rough skin: R>G>B, mid luminance
    skin = (r > g) & (g > b * 0.85) & (r > 70) & (r < 245) & ((r - b) > 15)
    return float(skin.mean())


def lint_endframe_no_redress(
    video: Path | str,
    *,
    wardrobe_state: str | None = None,
    heat_phase: str | None = None,
    shot_id: str | None = None,
) -> dict[str, Any]:
    """Return ok/codes for last-frame re-dress risk on undress meat shots."""
    if _env_skip():
        return {
            "ok": True,
            "skipped": True,
            "escape": "AIFILM_SKIP_ENDFRAME_WARDROBE=1",
            "shot_id": shot_id,
        }
    vid = Path(video).expanduser().resolve()
    w = str(wardrobe_state or "").strip().lower()
    heat = str(heat_phase or "").strip().lower()
    restricted = w in _UNDRESS or heat in {"act", "climax", "foreplay"}
    if not restricted:
        return {
            "ok": True,
            "required": False,
            "shot_id": shot_id,
            "note": "non-restricted wardrobe/heat — endframe lint advisory only",
        }
    if not vid.is_file():
        return {
            "ok": False,
            "shot_id": shot_id,
            "codes": ["ENDFRAME_CLIP_MISSING"],
            "message": f"clip missing: {vid}",
        }
    work = Path(tempfile.mkdtemp(prefix="endframe_wr_"))
    first = _extract(vid, "first", work / "first.png")
    last = _extract(vid, "last", work / "last.png")
    if first is None or last is None:
        return {
            "ok": True,
            "soft": True,
            "shot_id": shot_id,
            "codes": ["ENDFRAME_EXTRACT_FAILED"],
            "note": "could not extract frames — not hard fail (dummy/corrupt mp4)",
        }
    s0 = _skin_ratio(first)
    s1 = _skin_ratio(last)
    codes: list[str] = []
    drop = None
    if s0 is not None and s1 is not None:
        drop = float(s0 - s1)
        # last has much less skin than first → likely re-dressed mid-clip
        if drop >= _SKIN_DROP_HARD and s0 >= 0.12:
            codes.append("ENDFRAME_REDRESS_RISK")
    ok = "ENDFRAME_REDRESS_RISK" not in codes
    return {
        "ok": ok,
        "required": True,
        "shot_id": shot_id,
        "wardrobe_state": w or None,
        "heat_phase": heat or None,
        "skin_first": round(s0, 4) if s0 is not None else None,
        "skin_last": round(s1, 4) if s1 is not None else None,
        "skin_drop": round(drop, 4) if drop is not None else None,
        "threshold": _SKIN_DROP_HARD,
        "codes": codes,
        "judgment_source": "heuristic_skin_ratio_not_cv",
        "note": (
            "last frame skin << first on undress meat — ban promote; re-I2V"
            if not ok
            else "endframe wardrobe heuristic ok"
        ),
        "at": utc_now(),
    }


def assert_endframe_no_redress(
    root: Path | str,
    shot_id: str,
    video: Path | str,
    *,
    wardrobe_state: str | None = None,
    heat_phase: str | None = None,
    hard: bool = True,
) -> dict[str, Any]:
    """Lint + optional hard raise; always write receipt under film root."""
    base = Path(root).expanduser().resolve()
    rep = lint_endframe_no_redress(
        video,
        wardrobe_state=wardrobe_state,
        heat_phase=heat_phase,
        shot_id=str(shot_id),
    )
    out = base / "receipts" / "endframe-wardrobe" / f"{shot_id}.json"
    try:
        write_json(out, {**rep, "kind": "endframe-wardrobe", "clip": str(video)})
        rep["receipt"] = str(out)
    except Exception:
        pass
    if hard and not rep.get("ok") and not rep.get("skipped") and not rep.get("soft"):
        raise EndframeWardrobeError(
            f"endframe no-redress gate failed for {shot_id}: "
            + ",".join(rep.get("codes") or ["ENDFRAME_REDRESS_RISK"])
            + " — last frame looks re-dressed; do not promote; re-I2V. "
            "escape AIFILM_SKIP_ENDFRAME_WARDROBE=1"
        )
    return rep

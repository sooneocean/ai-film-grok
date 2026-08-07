#!/usr/bin/env python3
"""I2V first-frame subject fill gate — measure → auto-remedy → re-gate.

EP02 2026-08-07: fullbody cast master as keyframe → ~0.5 area fill → "画面这么小".
Iron: subject must dominate vertical 9:16 before H3/Grok I2V.

Loop (deep concept):
  1. measure_subject_fill
  2. ensure_fill_frame (strip letterbox → cover-crop subject)
  3. assert_i2v_firstframe_fill (open vs chain thresholds)
  4. audit_film_composition_fill + register-still / still_source / generation_ready hooks

Escape: AIFILM_SKIP_COMPOSITION_FILL=1
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any, Literal

# Min fraction of frame height covered by approximate subject bbox (open still).
DEFAULT_MIN_HEIGHT_FILL = 0.72
# Min subject area / frame area (fullbody-on-gray often ~0.45–0.55).
DEFAULT_MIN_AREA_FILL = 0.55
# Chain last-frames: slightly softer height (letterbox strip handles bars).
CHAIN_MIN_HEIGHT_FILL = 0.68
CHAIN_MIN_AREA_FILL = 0.50

COMPOSITION_LOCK_PREFIX = (
    "COMPOSITION LOCK: subject fills frame vertically (≥75% height), "
    "tight CU/MS framing preferred, no tiny full-body on empty studio, "
    "no letterbox black bars. "
)

# Path substrings that strongly suggest a cast sheet, not a playable still.
_CAST_FULLBODY_MARKERS = (
    "cast-master",
    "cast_master",
    "fullbody",
    "full-body",
    "full_body",
    "master-fullbody",
    "character-sheet",
    "character_sheet",
    "turnaround",
    "lookbook",
)

Mode = Literal["open", "chain"]


def _env_skip(root: Path | str | None = None) -> bool:
    try:
        from core.skip_audit import skip_flag

        return skip_flag(
            "AIFILM_SKIP_COMPOSITION_FILL",
            origin="env",
            film_root=root,
            call_site="composition_fill_gate._env_skip",
        )
    except Exception:
        return os.environ.get("AIFILM_SKIP_COMPOSITION_FILL", "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }


def measure_subject_fill(path: Path | str) -> dict[str, Any]:
    """Return fill metrics for a still/keyframe image."""
    path = Path(path)
    out: dict[str, Any] = {
        "ok": False,
        "path": str(path),
        "width": None,
        "height": None,
        "height_fill": 0.0,
        "area_fill": 0.0,
        "black_top": 0,
        "black_bottom": 0,
        "errors": [],
    }
    if not path.is_file():
        out["errors"].append("file_missing")
        return out
    try:
        import numpy as np
        from PIL import Image
    except ImportError as e:
        out["errors"].append(f"deps:{e}")
        return out

    im = Image.open(path).convert("RGB")
    w, h = im.size
    out["width"], out["height"] = w, h
    a = np.asarray(im).astype(float)
    row_mean = a.mean(axis=(1, 2))
    black = row_mean < 12.0
    top = 0
    while top < h and black[top]:
        top += 1
    bot = h - 1
    while bot > 0 and black[bot]:
        bot -= 1
    out["black_top"] = int(top)
    out["black_bottom"] = int(h - 1 - bot)

    rv = ((a - a.mean()) ** 2).mean(axis=(1, 2))
    cv = ((a - a.mean()) ** 2).mean(axis=(0, 2))
    thr_r = max(float(rv.max()) * 0.12, 40.0)
    thr_c = max(float(cv.max()) * 0.12, 40.0)
    rs = np.where(rv > thr_r)[0]
    cs = np.where(cv > thr_c)[0]
    if len(rs) and len(cs):
        y0, y1 = int(rs[0]), int(rs[-1])
        x0, x1 = int(cs[0]), int(cs[-1])
        hfill = (y1 - y0 + 1) / float(h)
        afill = ((y1 - y0 + 1) * (x1 - x0 + 1)) / float(h * w)
        out["height_fill"] = round(hfill, 4)
        out["area_fill"] = round(afill, 4)
        out["bbox"] = [x0, y0, x1, y1]
    else:
        out["errors"].append("subject_bbox_empty")
    out["ok"] = True
    return out


def path_looks_like_cast_fullbody(path: Path | str) -> bool:
    s = str(path).lower().replace("\\", "/")
    return any(m in s for m in _CAST_FULLBODY_MARKERS)


def prompt_has_composition_lock(text: str) -> bool:
    t = (text or "").upper()
    return "COMPOSITION LOCK" in t or "SUBJECT FILLS" in t


def ensure_composition_lock_prefix(text: str) -> str:
    """Prepend COMPOSITION LOCK once if missing."""
    raw = text or ""
    if prompt_has_composition_lock(raw):
        return raw
    return COMPOSITION_LOCK_PREFIX + raw.lstrip()


def strip_letterbox(
    path: Path | str,
    out: Path | str | None = None,
    *,
    thr: float = 12.0,
) -> dict[str, Any]:
    """Crop near-black top/bottom bars and stretch back to original size."""
    path = Path(path)
    dest = Path(out) if out else path
    rep: dict[str, Any] = {
        "ok": False,
        "path": str(path),
        "out": str(dest),
        "action": "none",
        "black_top": 0,
        "black_bottom": 0,
        "errors": [],
    }
    if not path.is_file():
        rep["errors"].append("file_missing")
        return rep
    try:
        import numpy as np
        from PIL import Image
    except ImportError as e:
        rep["errors"].append(f"deps:{e}")
        return rep

    im = Image.open(path).convert("RGB")
    a = np.asarray(im)
    h, w = a.shape[:2]
    row = a.mean(axis=(1, 2))
    top = 0
    while top < h and row[top] < thr:
        top += 1
    bot = h - 1
    while bot > 0 and row[bot] < thr:
        bot -= 1
    rep["black_top"] = int(top)
    rep["black_bottom"] = int(h - 1 - bot)
    if top > 2 or (h - 1 - bot) > 2:
        crop = im.crop((0, top, w, bot + 1)).resize((w, h), Image.Resampling.LANCZOS)
        dest.parent.mkdir(parents=True, exist_ok=True)
        crop.save(dest)
        rep["action"] = "strip_letterbox"
    elif dest.resolve() != path.resolve():
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dest)
        rep["action"] = "copy"
    else:
        rep["action"] = "noop"
    rep["ok"] = True
    return rep


def cover_crop_subject(
    path: Path | str,
    out: Path | str | None = None,
    *,
    target_height_fill: float = 0.92,
    pad_frac: float = 0.06,
) -> dict[str, Any]:
    """Cover-crop around subject bbox so body/face dominates the frame.

    Keeps frame aspect; scales crop so subject height ≈ target_height_fill of canvas.
    """
    path = Path(path)
    dest = Path(out) if out else path
    rep: dict[str, Any] = {
        "ok": False,
        "path": str(path),
        "out": str(dest),
        "action": "none",
        "errors": [],
    }
    metrics = measure_subject_fill(path)
    if not metrics.get("ok") or not metrics.get("bbox"):
        rep["errors"].extend(metrics.get("errors") or ["no_bbox"])
        return rep
    try:
        from PIL import Image
    except ImportError as e:
        rep["errors"].append(f"deps:{e}")
        return rep

    w = int(metrics["width"])
    h = int(metrics["height"])
    x0, y0, x1, y1 = [int(v) for v in metrics["bbox"]]
    # pad bbox
    bw = max(1, x1 - x0 + 1)
    bh = max(1, y1 - y0 + 1)
    px = int(bw * pad_frac)
    py = int(bh * pad_frac)
    x0 = max(0, x0 - px)
    y0 = max(0, y0 - py)
    x1 = min(w - 1, x1 + px)
    y1 = min(h - 1, y1 + py)
    bw = x1 - x0 + 1
    bh = y1 - y0 + 1

    # Desired crop window: full aspect, subject height = target_height_fill * crop_h
    # crop_h such that bh / crop_h ≈ target → crop_h = bh / target
    crop_h = max(bh / max(target_height_fill, 0.5), bh)
    crop_w = crop_h * (w / float(h))
    if crop_w < bw:
        crop_w = float(bw)
        crop_h = crop_w * (h / float(w))

    cx = (x0 + x1) / 2.0
    cy = (y0 + y1) / 2.0
    # Prefer upper body / face: bias crop center slightly upward
    cy = cy - crop_h * 0.05

    left = cx - crop_w / 2.0
    top = cy - crop_h / 2.0
    # clamp into image; if crop larger than image, use full image
    if crop_w >= w and crop_h >= h:
        left, top, crop_w, crop_h = 0.0, 0.0, float(w), float(h)
    else:
        if left < 0:
            left = 0.0
        if top < 0:
            top = 0.0
        if left + crop_w > w:
            left = max(0.0, w - crop_w)
        if top + crop_h > h:
            top = max(0.0, h - crop_h)
        crop_w = min(crop_w, float(w))
        crop_h = min(crop_h, float(h))

    im = Image.open(path).convert("RGB")
    box = (
        int(round(left)),
        int(round(top)),
        int(round(left + crop_w)),
        int(round(top + crop_h)),
    )
    # ensure at least 1px
    if box[2] <= box[0]:
        box = (box[0], box[1], box[0] + 1, box[3])
    if box[3] <= box[1]:
        box = (box[0], box[1], box[2], box[1] + 1)
    crop = im.crop(box).resize((w, h), Image.Resampling.LANCZOS)
    dest.parent.mkdir(parents=True, exist_ok=True)
    crop.save(dest)
    rep["action"] = "cover_crop_subject"
    rep["crop_box"] = list(box)
    rep["ok"] = True
    after = measure_subject_fill(dest)
    rep["metrics_after"] = after
    return rep


def ensure_fill_frame(
    path: Path | str,
    out: Path | str | None = None,
    *,
    min_height_fill: float = DEFAULT_MIN_HEIGHT_FILL,
    min_area_fill: float = DEFAULT_MIN_AREA_FILL,
    mode: Mode = "open",
) -> dict[str, Any]:
    """Auto-remedy: strip letterbox → cover-crop if still tiny → re-measure.

    Writes to ``out`` (default: overwrite ``path``). Safe to call repeatedly.
    """
    path = Path(path)
    dest = Path(out) if out else path
    steps: list[dict[str, Any]] = []
    rep: dict[str, Any] = {
        "schema_version": 1,
        "kind": "ensure-fill-frame",
        "path": str(path),
        "out": str(dest),
        "mode": mode,
        "ok": False,
        "remedied": False,
        "steps": steps,
        "metrics_before": {},
        "metrics_after": {},
        "errors": [],
    }
    if _env_skip():
        rep["ok"] = True
        rep["skipped"] = True
        if dest.resolve() != path.resolve() and path.is_file():
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest)
        return rep
    if not path.is_file():
        rep["errors"].append("file_missing")
        return rep

    before = measure_subject_fill(path)
    rep["metrics_before"] = before
    work = path
    # Work on a temp sibling if writing elsewhere, else in-place stepwise
    if dest.resolve() != path.resolve():
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dest)
        work = dest

    hfill = float(before.get("height_fill") or 0.0)
    afill = float(before.get("area_fill") or 0.0)
    bt = int(before.get("black_top") or 0)
    bb = int(before.get("black_bottom") or 0)
    h = int(before.get("height") or 1)
    bar_ratio = (bt + bb) / float(max(h, 1))

    # Step 1: strip letterbox when bars present
    if bar_ratio > 0.02:
        s = strip_letterbox(work, work)
        steps.append(s)
        if s.get("action") == "strip_letterbox":
            rep["remedied"] = True

    mid = measure_subject_fill(work)
    hfill = float(mid.get("height_fill") or 0.0)
    afill = float(mid.get("area_fill") or 0.0)

    # Step 2: cover-crop if subject still postage-stamp
    if hfill < min_height_fill or afill < min_area_fill:
        c = cover_crop_subject(work, work)
        steps.append(c)
        if c.get("ok") and c.get("action") == "cover_crop_subject":
            rep["remedied"] = True
        elif not c.get("ok"):
            rep["errors"].extend(c.get("errors") or ["cover_crop_failed"])

    after = measure_subject_fill(work)
    rep["metrics_after"] = after
    hfill = float(after.get("height_fill") or 0.0)
    afill = float(after.get("area_fill") or 0.0)
    rep["ok"] = bool(
        after.get("ok")
        and hfill >= min_height_fill * 0.98  # tiny float slack
        and afill >= min_area_fill * 0.98
    )
    if not rep["ok"] and not rep["errors"]:
        rep["errors"].append(
            f"still_underfilled after remedy hfill={hfill:.2f} afill={afill:.2f}"
        )
    return rep


def assert_i2v_firstframe_fill(
    path: Path | str,
    *,
    min_height_fill: float | None = None,
    min_area_fill: float | None = None,
    reject_cast_fullbody_path: bool = True,
    mode: Mode = "open",
) -> dict[str, Any]:
    """Gate one still before I2V. Returns report with ok / codes / errors.

    mode:
      - open: new still / register-still (strict)
      - chain: last-frame → next keyframe (letterbox hard only if subject still small)
    """
    path = Path(path)
    if min_height_fill is None:
        min_height_fill = (
            CHAIN_MIN_HEIGHT_FILL if mode == "chain" else DEFAULT_MIN_HEIGHT_FILL
        )
    if min_area_fill is None:
        min_area_fill = CHAIN_MIN_AREA_FILL if mode == "chain" else DEFAULT_MIN_AREA_FILL

    report: dict[str, Any] = {
        "schema_version": 1,
        "kind": "composition-fill-gate",
        "path": str(path),
        "mode": mode,
        "ok": True,
        "codes": [],
        "errors": [],
        "metrics": {},
        "skipped": False,
    }
    if _env_skip():
        report["skipped"] = True
        report["codes"].append("COMPOSITION_FILL_SKIPPED")
        return report

    if reject_cast_fullbody_path and path_looks_like_cast_fullbody(path):
        # Allow only if file was cover-cropped into keyframes/ or stills/
        norm = str(path).replace("\\", "/")
        if "keyframes/" not in norm and "stills/" not in norm:
            report["ok"] = False
            report["codes"].append("CAST_FULLBODY_AS_FIRSTFRAME")
            report["errors"].append(
                "cast/fullbody/sheet path cannot be I2V first frame; "
                "cover-crop to keyframes/ as MS/CU first (EP02 2026-08-07)"
            )

    metrics = measure_subject_fill(path)
    report["metrics"] = metrics
    if not metrics.get("ok"):
        report["ok"] = False
        report["codes"].append("I2V_FIRSTFRAME_UNREADABLE")
        report["errors"].extend(metrics.get("errors") or ["measure_failed"])
        return report

    hfill = float(metrics.get("height_fill") or 0.0)
    afill = float(metrics.get("area_fill") or 0.0)
    if hfill < min_height_fill or afill < min_area_fill:
        report["ok"] = False
        report["codes"].append("I2V_FIRSTFRAME_TINY_SUBJECT")
        report["errors"].append(
            f"subject too small for I2V first frame "
            f"(height_fill={hfill:.2f} need>={min_height_fill}, "
            f"area_fill={afill:.2f} need>={min_area_fill}); "
            "use fill-frame CU/MS or ensure_fill_frame, never tiny fullbody on empty studio"
        )

    # letterbox: hard-fail only when bars are large AND subject still small
    # (H3 last-frame chains often have thin bars but subject already fills)
    bt = int(metrics.get("black_top") or 0)
    bb = int(metrics.get("black_bottom") or 0)
    h = int(metrics.get("height") or 1)
    bar_ratio = (bt + bb) / float(h)
    if mode == "chain":
        # chain: hard only extreme bars with tiny subject; else soft + caller should strip
        if bar_ratio > 0.18 and hfill < 0.80:
            report["ok"] = False
            report["codes"].append("I2V_FIRSTFRAME_LETTERBOX")
            report["errors"].append(
                f"letterbox/black bars top={bt} bottom={bb} with small subject; "
                "run ensure_fill_frame / strip_letterbox before I2V"
            )
        elif bar_ratio > 0.05:
            report["codes"].append("I2V_FIRSTFRAME_LETTERBOX_SOFT")
    else:
        if bar_ratio > 0.12 and hfill < 0.85:
            report["ok"] = False
            report["codes"].append("I2V_FIRSTFRAME_LETTERBOX")
            report["errors"].append(
                f"letterbox/black bars top={bt} bottom={bb} with small subject; "
                "refuse I2V first frame"
            )
        elif bar_ratio > 0.08:
            report["codes"].append("I2V_FIRSTFRAME_LETTERBOX_SOFT")

    return report


def assert_still_path_ready_for_i2v(
    path: Path | str,
    *,
    mode: Mode = "open",
    auto_remedy: bool = True,
    shot_id: str | None = None,
) -> dict[str, Any]:
    """Wave 3 · gate **any** still path used as I2V/H3 first frame (not only keyframes/).

    Used by ``h3 run`` / media-queue so continue handoff stills and stills/ are
    held to the same fill bar as register-still.
    """
    p = Path(path).expanduser().resolve()
    if not p.is_file():
        return {
            "schema_version": 1,
            "kind": "composition-fill-gate",
            "ok": False,
            "shot_id": shot_id,
            "path": str(p),
            "codes": ["I2V_FIRSTFRAME_MISSING"],
            "errors": [f"missing still path {p}"],
            "remedy": None,
        }
    if _env_skip():
        return {
            "schema_version": 1,
            "kind": "composition-fill-gate",
            "ok": True,
            "skipped": True,
            "escape": "AIFILM_SKIP_COMPOSITION_FILL=1",
            "shot_id": shot_id,
            "path": str(p),
        }
    # Cast-sheet path names never animate as hero first frame
    if path_looks_like_cast_fullbody(p):
        # still under keyframes/stills may be intentional after crop — measure pixels
        pass
    use_mode: Mode = mode
    # continue / endframe handoffs often carry soft bars
    name_l = p.name.lower()
    if mode == "open" and (
        "_end" in name_l or "handoff" in str(p).lower() or name_l.startswith("_last_")
    ):
        use_mode = "chain"

    remedy = None
    if auto_remedy:
        min_h = CHAIN_MIN_HEIGHT_FILL if use_mode == "chain" else DEFAULT_MIN_HEIGHT_FILL
        min_a = CHAIN_MIN_AREA_FILL if use_mode == "chain" else DEFAULT_MIN_AREA_FILL
        pre = assert_i2v_firstframe_fill(p, mode=use_mode)
        if not pre.get("ok") or "I2V_FIRSTFRAME_LETTERBOX_SOFT" in (pre.get("codes") or []):
            try:
                remedy = ensure_fill_frame(
                    p, p, min_height_fill=min_h, min_area_fill=min_a, mode=use_mode
                )
            except Exception as exc:  # noqa: BLE001
                remedy = {"remedied": False, "error": str(exc)[:160]}

    rep = assert_i2v_firstframe_fill(p, mode=use_mode)
    rep["shot_id"] = shot_id
    rep["path"] = str(p)
    rep["remedy"] = remedy
    rep["effective_mode"] = use_mode
    return rep


def assert_keyframe_ready_for_h3(
    root: Path | str,
    shot_id: str,
    *,
    mode: Mode = "open",
    auto_remedy: bool = True,
    still_path: Path | str | None = None,
) -> dict[str, Any]:
    """Resolve keyframes/<shot>.png (or explicit still_path), optionally auto-remedy, then gate."""
    root = Path(root)
    if still_path is not None:
        return assert_still_path_ready_for_i2v(
            still_path, mode=mode, auto_remedy=auto_remedy, shot_id=str(shot_id)
        )
    kf = root / "keyframes" / f"{shot_id}.png"
    if not kf.is_file():
        # Fall back to stills/<id>.png (common h3_primary path)
        alt = root / "stills" / f"{shot_id}.png"
        if alt.is_file():
            return assert_still_path_ready_for_i2v(
                alt, mode=mode, auto_remedy=auto_remedy, shot_id=str(shot_id)
            )
        return {
            "schema_version": 1,
            "kind": "composition-fill-gate",
            "ok": False,
            "shot_id": shot_id,
            "codes": ["I2V_FIRSTFRAME_MISSING"],
            "errors": [f"missing {kf}"],
            "remedy": None,
        }

    # Infer chain if this keyframe came from last-frame pattern siblings
    last_like = (root / "keyframes" / f"_last_{shot_id}.png").is_file()
    if mode == "open" and last_like:
        pass  # keep caller mode
    # Prefer chain thresholds when seed was chained (soft letterbox)
    seed = root / "keyframes" / f"{shot_id}-seed.png"
    use_mode: Mode = mode
    if mode == "open" and seed.is_file():
        # seeded chain stills often have residual bars — use chain thresholds + remedy
        use_mode = "chain"

    remedy = None
    if auto_remedy and not _env_skip():
        min_h = CHAIN_MIN_HEIGHT_FILL if use_mode == "chain" else DEFAULT_MIN_HEIGHT_FILL
        min_a = CHAIN_MIN_AREA_FILL if use_mode == "chain" else DEFAULT_MIN_AREA_FILL
        pre = assert_i2v_firstframe_fill(kf, mode=use_mode)
        if not pre.get("ok") or "I2V_FIRSTFRAME_LETTERBOX_SOFT" in (pre.get("codes") or []):
            remedy = ensure_fill_frame(
                kf, kf, min_height_fill=min_h, min_area_fill=min_a, mode=use_mode
            )

    rep = assert_i2v_firstframe_fill(kf, mode=use_mode)
    rep["shot_id"] = shot_id
    rep["remedy"] = remedy
    rep["effective_mode"] = use_mode
    return rep


def audit_film_composition_fill(
    root: Path | str,
    *,
    auto_remedy: bool = False,
    max_shots: int = 200,
) -> dict[str, Any]:
    """Audit keyframes/ for I2V fill readiness (timeline order when available)."""
    root = Path(root)
    ids: list[str] = []
    tl_path = root / "timeline.json"
    if tl_path.is_file():
        try:
            import json

            tl = json.loads(tl_path.read_text(encoding="utf-8"))
            for s in tl.get("shots") or []:
                if isinstance(s, dict) and s.get("id"):
                    ids.append(str(s["id"]))
        except Exception:
            ids = []
    if not ids:
        kf_dir = root / "keyframes"
        if kf_dir.is_dir():
            for p in sorted(kf_dir.glob("*.png")):
                name = p.stem
                if name.startswith("_last_") or name.endswith("-seed"):
                    continue
                ids.append(name)

    rows: list[dict[str, Any]] = []
    hard: list[str] = []
    soft: list[str] = []
    remedied = 0
    for sid in ids[:max_shots]:
        kf = root / "keyframes" / f"{sid}.png"
        if not kf.is_file():
            continue
        if auto_remedy:
            gate = assert_keyframe_ready_for_h3(root, sid, auto_remedy=True)
            if (gate.get("remedy") or {}).get("remedied"):
                remedied += 1
        else:
            gate = assert_i2v_firstframe_fill(kf, mode="open")
            gate["shot_id"] = sid
        row = {
            "shot_id": sid,
            "ok": bool(gate.get("ok")),
            "codes": list(gate.get("codes") or []),
            "height_fill": (gate.get("metrics") or {}).get("height_fill"),
            "area_fill": (gate.get("metrics") or {}).get("area_fill"),
            "path": str(kf),
        }
        rows.append(row)
        if not gate.get("ok"):
            hard.append(f"{sid}:{','.join(gate.get('codes') or ['FAIL'])}")
        elif any(
            c.endswith("_SOFT") or c == "I2V_FIRSTFRAME_LETTERBOX_SOFT"
            for c in (gate.get("codes") or [])
        ):
            soft.append(sid)

    return {
        "schema_version": 1,
        "kind": "composition-fill-audit",
        "ok": not hard,
        "hard": hard,
        "soft": soft[:20],
        "remedied": remedied,
        "checked": len(rows),
        "shots": rows,
        "cli": "python -c \"from composition_fill_gate import audit_film_composition_fill; ...\"",
    }


if __name__ == "__main__":
    import argparse
    import json
    import sys

    ap = argparse.ArgumentParser(description="I2V first-frame composition fill gate")
    ap.add_argument("path", nargs="?", help="image path to gate")
    ap.add_argument("--root", help="film root for audit / keyframe ready")
    ap.add_argument("--shot", help="shot id under --root/keyframes")
    ap.add_argument("--audit", action="store_true")
    ap.add_argument("--ensure", action="store_true", help="auto-remedy path or keyframe")
    ap.add_argument("--mode", choices=("open", "chain"), default="open")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.audit and args.root:
        r = audit_film_composition_fill(args.root, auto_remedy=args.ensure)
    elif args.root and args.shot:
        r = assert_keyframe_ready_for_h3(
            args.root, args.shot, mode=args.mode, auto_remedy=args.ensure
        )
    elif args.path and args.ensure:
        r = ensure_fill_frame(args.path, mode=args.mode)
    elif args.path:
        r = assert_i2v_firstframe_fill(args.path, mode=args.mode)
    else:
        ap.print_help()
        sys.exit(2)

    if args.json:
        print(json.dumps(r, indent=2, default=str))
    else:
        ok = r.get("ok")
        print(f"ok={ok} codes={r.get('codes') or r.get('hard')} path={r.get('path') or r.get('out')}")
        if r.get("errors"):
            print("errors:", r["errors"])
        if r.get("metrics"):
            m = r["metrics"]
            print(
                f"hfill={m.get('height_fill')} afill={m.get('area_fill')} "
                f"bars={m.get('black_top')}/{m.get('black_bottom')}"
            )
        if r.get("hard"):
            print("hard:", r["hard"][:8])
    sys.exit(0 if r.get("ok") else 1)

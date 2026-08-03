#!/usr/bin/env python3
"""Staged final delivery — no assumed captions.

P0 · 2026-07-23 (E-virus / empty-subs recurrence):

Tasks are separate and ordered. Nothing is assumed to "just burn".

  stage_plate     → FFmpeg plate: VO + BGM + clips, **subs off**, blank cards
  stage_hf        → HyperFrames export+render owns **designed captions**
  stage_caption   → verify caption ownership in the delivery MP4; if HF did not
                    put readable captions in pixels, run explicit PIL burn recovery
  stage_deliver   → write final-stages.json + patch final-delivery burned_in

HyperFrames is the intended caption owner when --post-engine hyperframes.
PIL burn is a **named recovery stage**, never a silent assumption that HF worked.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

from security_policy import minimal_subprocess_env
from util import read_json as _util_read_json
from util import sha256_file as _sha256
from util import utc_now, write_json


def _read_json(path: Path) -> dict[str, Any]:
    """Soft local: missing/invalid JSON becomes {} (stage receipts)."""
    return _util_read_json(path) or {}


def inspect_hf_caption_export(root: Path) -> dict[str, Any]:
    """Inspect HF export artifacts for caption placement (not pixel burn)."""
    root = Path(root).expanduser().resolve()
    receipt = root / "compose" / "hyperframes" / "media-stage-receipt.json"
    index = root / "compose" / "hyperframes" / "index.html"
    placed = 0
    receipt_data = _read_json(receipt)
    if isinstance(receipt_data.get("captions_placed"), int):
        placed = int(receipt_data["captions_placed"])
    html_caps = 0
    if index.is_file():
        html = index.read_text(encoding="utf-8", errors="replace")
        html_caps = html.count('class="clip caption"') + html.count("class='clip caption'")
    srt = root / "out" / "final.srt"
    srt_ok = srt.is_file() and srt.stat().st_size > 20
    ok = (placed > 0 or html_caps > 0) and srt_ok
    return {
        "ok": ok,
        "captions_placed_receipt": placed,
        "captions_in_index_html": html_caps,
        "srt_present": srt_ok,
        "srt": str(srt) if srt_ok else None,
        "receipt": str(receipt) if receipt.is_file() else None,
        "index": str(index) if index.is_file() else None,
        "note": (
            "export has caption clips + SRT"
            if ok
            else "HF export missing captions or SRT — cannot claim HF owns subtitles"
        ),
    }


def sample_bottom_band_activity(
    video: Path,
    *,
    timestamps: list[float],
    height_ratio: float = 0.14,
) -> dict[str, Any]:
    """Cheap pixel heuristic: subtitle bar usually darkens/varies bottom band.

    Not OCR. Used only as a soft signal; combined with HF export inspection.
    """
    try:
        from PIL import Image
    except ImportError:
        return {"ok": None, "error": "PIL missing", "samples": []}

    samples: list[dict[str, Any]] = []
    for ts in timestamps:
        tmp = video.parent / f"_cap_probe_{ts:.3f}.png"
        proc = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-v",
                "error",
                "-ss",
                f"{ts:.3f}",
                "-i",
                str(video),
                "-frames:v",
                "1",
                str(tmp),
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
            env=minimal_subprocess_env(),
        )
        if proc.returncode != 0 or not tmp.is_file():
            samples.append({"ts": ts, "ok": False, "error": "extract_failed"})
            continue
        im = Image.open(tmp).convert("L")
        w, h = im.size
        y0 = int(h * (1.0 - height_ratio))
        band = im.crop((0, y0, w, h))
        # variance proxy: range of brightness
        extrema = band.getextrema()
        lo, hi = float(extrema[0]), float(extrema[1])
        contrast = hi - lo
        mean = sum(band.getdata()) / max(1, band.size[0] * band.size[1])
        # burned captions: dark bar + light glyphs → contrast often > 40
        likely = contrast >= 35 and mean < 200
        samples.append(
            {
                "ts": ts,
                "ok": True,
                "contrast": round(contrast, 1),
                "mean": round(mean, 1),
                "likely_caption_bar": likely,
                "path": str(tmp),
            }
        )
    likely_n = sum(1 for s in samples if s.get("likely_caption_bar"))
    return {
        "ok": likely_n >= max(1, len(samples) // 2) if samples else False,
        "likely_count": likely_n,
        "sample_count": len(samples),
        "samples": samples,
    }


def run_pil_caption_burn(root: Path, *, video: Path, srt: Path, out: Path) -> dict[str, Any]:
    """Explicit recovery stage: burn SRT with PIL overlays (no libass)."""
    scripts = Path(__file__).resolve().parent
    burn = scripts / "burn_srt_pil.py"
    if not burn.is_file():
        return {"ok": False, "error": f"missing {burn}"}
    cmd = [
        sys.executable,
        str(burn),
        "--video",
        str(video),
        "--srt",
        str(srt),
        "--out",
        str(out),
    ]
    proc = subprocess.run(
        cmd, capture_output=True, text=True, timeout=900, check=False, env=minimal_subprocess_env()
    )
    return {
        "ok": proc.returncode == 0 and out.is_file(),
        "returncode": proc.returncode,
        "stdout": (proc.stdout or "")[-1500:],
        "stderr": (proc.stderr or "")[-1500:],
        "out": str(out),
        "sha256": _sha256(out) if out.is_file() else None,
    }


def ensure_captions_after_hf(root: Path, *, final_mp4: Path) -> dict[str, Any]:
    """Fail closed unless HyperFrames is the verified caption owner."""
    root = Path(root).expanduser().resolve()
    final_mp4 = Path(final_mp4).expanduser().resolve()
    srt = root / "out" / "final.srt"
    export_gate = inspect_hf_caption_export(root)

    # Probe mid-cue timestamps from SRT if present
    timestamps = [5.0, 20.0, 50.0]
    if srt.is_file():
        try:
            from subtitle_dialogue_alignment import _cues

            cues = _cues(srt)
            if cues:
                idxs = [0, len(cues) // 2, len(cues) - 1]
                timestamps = []
                for i in idxs:
                    start, end = cues[i]
                    timestamps.append(round(start + max(0.05, (end - start) / 2), 3))
        except Exception:
            pass

    pixel = (
        sample_bottom_band_activity(final_mp4, timestamps=timestamps)
        if final_mp4.is_file()
        else {"ok": False, "error": "final missing"}
    )

    report: dict[str, Any] = {
        "stage": "caption",
        "at": utc_now(),
        "export_gate": export_gate,
        "pixel_probe": pixel,
        "caption_owner": None,
        "ok": False,
        "recovery": None,
    }

    # HF path success: export has captions AND pixel probe likely
    if export_gate.get("ok") and pixel.get("ok") is True:
        report["caption_owner"] = "hyperframes"
        report["ok"] = True
        report["note"] = "HF export captions present; bottom-band probe likely burned-in"
        return report

    if export_gate.get("ok") and pixel.get("ok") is None:
        # No PIL / probe inconclusive — still trust export only if HTML has many caps
        if int(export_gate.get("captions_in_index_html") or 0) >= 3:
            report["caption_owner"] = "hyperframes_export_only"
            report["ok"] = True
            report["note"] = "pixel probe unavailable; export captions accepted with caution"
            return report

    report["caption_owner"] = "missing"
    report["ok"] = False
    report["error"] = "HF caption gate failed; repair the HyperFrames captions and re-render"
    return report


def patch_delivery_burned_in(root: Path, *, burned_in: bool, owner: str) -> dict[str, Any]:
    path = root / "out" / "final-delivery.json"
    data = _read_json(path)
    subs = data.get("subtitles") if isinstance(data.get("subtitles"), dict) else {}
    subs["burned_in"] = burned_in
    subs["caption_owner"] = owner
    subs["caption_stages_at"] = utc_now()
    data["subtitles"] = subs
    write_json(path, data)
    return {"path": str(path), "burned_in": burned_in, "caption_owner": owner}


def write_stages_receipt(root: Path, stages: dict[str, Any]) -> Path:
    path = root / "receipts" / "final-stages.json"
    payload = {
        "schema_version": 1,
        "kind": "final-stages",
        "at": utc_now(),
        "root": str(root),
        "stages": stages,
        "contract": [
            "plate: render_final --subs off (no captions assumed)",
            "hf: HyperFrames export+render owns designed captions",
            "caption: verify pixels; pil_recovery only as named stage",
            "deliver: burned_in reflects actual owner",
        ],
    }
    write_json(path, payload)
    return path

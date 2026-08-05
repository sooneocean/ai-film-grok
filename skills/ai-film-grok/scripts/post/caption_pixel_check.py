#!/usr/bin/env python3
"""Caption pixel ink check — bowl has soup, not just menu says soup.

P0 · 2026-08-05: machine gate that final MP4 bottom-band looks like burned captions
at SRT cue midpoints. Not OCR. Human attestation remains optional soft for ship;
closeout treats missing_ink as hard when SRT has dialogue cues.

Receipt: ``receipts/caption-pixel-check.json``
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from util import read_json, sha256_file, utc_now, write_json

RECEIPT_REL = Path("receipts/caption-pixel-check.json")


class CaptionPixelError(ValueError):
    """Pixel caption check failed hard."""


def _first_file(root: Path, *relative: str) -> Path | None:
    return next((root / item for item in relative if (root / item).is_file()), None)


def _skip_enabled() -> bool:
    return str(os.environ.get("AIFILM_SKIP_CAPTION_PIXEL") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _cue_mid_timestamps(srt: Path, *, max_samples: int = 5) -> list[float]:
    try:
        from subtitle_dialogue_alignment import _cues

        cues = _cues(srt)
    except Exception:
        cues = []
    if not cues:
        return [1.0, 3.0]
    from caption_frame_audit import sample_cue_indices

    idxs = sample_cue_indices(len(cues), max_frames=max_samples)
    out: list[float] = []
    for i in idxs:
        start, end = cues[i]
        out.append(round(start + max(0.05, (end - start) / 2), 3))
    return out or [1.0]


def run_caption_pixel_check(
    root: Path | str,
    *,
    max_samples: int = 5,
    write: bool = True,
    final_mp4: Path | str | None = None,
) -> dict[str, Any]:
    """Probe final MP4 bottom band at cue mids; write durable receipt."""
    base = Path(root).expanduser().resolve()
    if _skip_enabled():
        report = {
            "schema_version": 1,
            "kind": "caption-pixel-check",
            "at": utc_now(),
            "ok": True,
            "skipped": True,
            "reason": "AIFILM_SKIP_CAPTION_PIXEL=1",
            "missing_ink": False,
        }
        if write:
            path = base / RECEIPT_REL
            write_json(path, report)
            report["path"] = str(path)
        return report

    final = Path(final_mp4).expanduser().resolve() if final_mp4 else None
    if final is None or not final.is_file():
        final = _first_file(base, "out/film_final.mp4", "out/final.mp4", "final.mp4")
    srt = _first_file(base, "out/final.srt", "final.srt")

    if final is None:
        report = {
            "schema_version": 1,
            "kind": "caption-pixel-check",
            "at": utc_now(),
            "ok": False,
            "missing_ink": True,
            "error": "no final MP4 for caption pixel check",
            "next_cmd": f'aifilm final --root "{base}" --tts-backend edge --music-mood rnb',
        }
        if write:
            path = base / RECEIPT_REL
            write_json(path, report)
            report["path"] = str(path)
        return report

    if srt is None:
        report = {
            "schema_version": 1,
            "kind": "caption-pixel-check",
            "at": utc_now(),
            "ok": False,
            "missing_ink": True,
            "final": {"path": str(final), "sha256": sha256_file(final)},
            "error": "no final.srt — cannot align cue samples",
            "next_cmd": f'aifilm final --root "{base}"',
        }
        if write:
            path = base / RECEIPT_REL
            write_json(path, report)
            report["path"] = str(path)
        return report

    timestamps = _cue_mid_timestamps(srt, max_samples=max_samples)
    from final_stages import sample_bottom_band_activity

    probe = sample_bottom_band_activity(final, timestamps=timestamps)
    likely = int(probe.get("likely_count") or 0)
    sample_n = int(probe.get("sample_count") or 0)
    # Need majority of samples to look like a caption bar when SRT has cues
    ok_probe = probe.get("ok") is True
    inconclusive = probe.get("ok") is None
    missing_ink = (not ok_probe) and (not inconclusive)

    # Prefer post-route caption_path for messaging
    route = read_json(base / "receipts" / "post-route.json") or {}
    caption_path = route.get("caption_path")

    report = {
        "schema_version": 1,
        "kind": "caption-pixel-check",
        "at": utc_now(),
        "ok": bool(ok_probe),
        "missing_ink": bool(missing_ink),
        "inconclusive": bool(inconclusive),
        "caption_path": caption_path,
        "final": {"path": str(final), "sha256": sha256_file(final)},
        "subtitles": {
            "path": str(srt),
            "sha256": sha256_file(srt),
        },
        "cues_checked": sample_n,
        "likely_count": likely,
        "timestamps": timestamps,
        "pixel_probe": {
            "ok": probe.get("ok"),
            "likely_count": likely,
            "sample_count": sample_n,
            "error": probe.get("error"),
            # drop heavy sample paths in receipt samples summary
            "samples": [
                {
                    "ts": s.get("ts"),
                    "likely_caption_bar": s.get("likely_caption_bar"),
                    "contrast": s.get("contrast"),
                    "mean": s.get("mean"),
                    "ok": s.get("ok"),
                }
                for s in (probe.get("samples") or [])
                if isinstance(s, dict)
            ],
        },
        "method": "bottom_band_contrast_heuristic_v1",
        "note": (
            "ok=True means bottom band looks like burned caption ink at cue mids; "
            "not OCR. Human caption-frame-attest still available for formal review."
        ),
    }
    if missing_ink:
        report["error"] = (
            "caption pixel ink missing at cue midpoints "
            f"(likely_count={likely}/{sample_n}). Re-burn ship_hardburn or fix HF captions."
        )
        report["next_cmd"] = (
            f'aifilm final --root "{base}" --caption-path ship_hardburn --post-engine ffmpeg '
            f"--tts-backend edge --music-mood rnb"
        )
    elif inconclusive:
        report["ok"] = False
        report["error"] = probe.get("error") or "pixel probe inconclusive (e.g. PIL missing)"
        report["next_cmd"] = f'aifilm caption-pixel-check --root "{base}"'
    if write:
        path = base / RECEIPT_REL
        write_json(path, report)
        report["path"] = str(path)
    return report


def caption_pixel_status(root: Path | str) -> dict[str, Any]:
    """Read-only freshness against current final/srt hashes."""
    base = Path(root).expanduser().resolve()
    if _skip_enabled():
        return {
            "ok": True,
            "skipped": True,
            "present": True,
            "stale": False,
            "missing_ink": False,
        }
    path = base / RECEIPT_REL
    report = read_json(path) or {}
    final = _first_file(base, "out/film_final.mp4", "out/final.mp4", "final.mp4")
    srt = _first_file(base, "out/final.srt", "final.srt")
    current = {
        "final": sha256_file(final) if final else None,
        "subtitles": sha256_file(srt) if srt else None,
    }
    bound = {
        "final": (report.get("final") or {}).get("sha256"),
        "subtitles": (report.get("subtitles") or {}).get("sha256"),
    }
    present = report.get("kind") == "caption-pixel-check"
    stale = present and any(current[k] != bound[k] for k in current)
    ok = bool(report.get("ok")) and present and not stale and not report.get("missing_ink")
    return {
        "ok": ok,
        "present": present,
        "stale": stale,
        "missing_ink": bool(report.get("missing_ink")),
        "inconclusive": bool(report.get("inconclusive")),
        "current": current,
        "bound": bound,
        "path": str(path) if path.is_file() else None,
        "next_cmd": report.get("next_cmd") or f'aifilm caption-pixel-check --root "{base}"',
        "detail": (
            "ok"
            if ok
            else (
                "stale — re-run caption-pixel-check after final changed"
                if stale
                else report.get("error")
                or ("missing receipt" if not present else "pixel check red")
            )
        ),
    }


def assert_caption_pixels_for_closeout(
    root: Path | str, *, write_if_missing: bool = True
) -> dict[str, Any]:
    """Hard gate for closeout/export when dialogue SRT exists."""
    base = Path(root).expanduser().resolve()
    if _skip_enabled():
        return caption_pixel_status(base)
    status = caption_pixel_status(base)
    if status.get("ok"):
        return status
    if write_if_missing or status.get("stale") or not status.get("present"):
        report = run_caption_pixel_check(base, write=True)
        status = caption_pixel_status(base)
        if report.get("ok") and status.get("ok"):
            return status
        if report.get("missing_ink") or not report.get("ok"):
            raise CaptionPixelError(
                report.get("error") or status.get("detail") or "caption pixel check failed"
            )
    if not status.get("ok"):
        raise CaptionPixelError(status.get("detail") or "caption pixel check failed")
    return status


def evidence_stale_after_final(root: Path | str) -> dict[str, Any]:
    """Detect quality-report / narrative / caption receipts stale vs final sha."""
    base = Path(root).expanduser().resolve()
    final = _first_file(base, "out/film_final.mp4", "out/final.mp4", "final.mp4")
    final_sha = sha256_file(final) if final else None
    issues: list[dict[str, str]] = []
    actions: list[str] = []

    qr = base / "out" / "quality-report.json"
    if final and qr.is_file():
        data = read_json(qr) or {}
        bound = (
            data.get("media_sha256")
            or data.get("final_sha256")
            or (data.get("final") or {}).get("sha256")
        )
        if bound and final_sha and str(bound) != str(final_sha):
            issues.append({"code": "QUALITY_REPORT_STALE", "detail": "quality-report sha ≠ final"})
            actions.append(f'rm -f "{qr}"')

    # caption pixel — only when dialogue SRT exists
    srt = _first_file(base, "out/final.srt", "final.srt")
    if final and srt is not None:
        cap = caption_pixel_status(base)
        if cap.get("stale") or (not cap.get("present") and final.is_file()):
            issues.append({"code": "CAPTION_PIXEL_STALE", "detail": cap.get("detail") or "stale"})
            actions.append(f'aifilm caption-pixel-check --root "{base}"')

    # mix partial honesty
    mix = read_json(base / "receipts" / "final-mix-partial.json") or {}
    mix_partial = False
    if mix and (
        mix.get("kind") == "final-mix-partial"
        or mix.get("partial") is True
        or mix.get("ok") is False
    ):
        mix_partial = True

    return {
        "ok": len(issues) == 0,
        "final_sha256": final_sha,
        "issues": issues,
        "actions": actions,
        "mix_partial": bool(mix_partial),
        "next_cmd": actions[0] if actions else None,
        "honest_limits": (
            ["final_mix_partial — sidechain degraded; not full five-track cinema mix"]
            if mix_partial
            else []
        ),
    }

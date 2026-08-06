"""H3 native-audio season ship path (Q5.1 · savani lessons).

Concat approved clips in timeline order, keep clip aac when present.
Optional soft path: no TTS re-render, no canonical-truth gate.

Honest delivery class: OFFICIAL_FINAL_PLATE (not master_lock).
Does not replace gate-auto green master.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from util import read_json, utc_now, write_json


class H3ShipNativeError(RuntimeError):
    pass


def _flatten_shots(spec: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for scene in spec.get("scenes") or []:
        if not isinstance(scene, dict):
            continue
        for sh in scene.get("shots") or []:
            if isinstance(sh, dict):
                out.append(sh)
    if not out and isinstance(spec.get("shots"), list):
        for sh in spec["shots"]:
            if isinstance(sh, dict):
                out.append(sh)
    return out


def _clip_path(root: Path, rec: dict[str, Any]) -> Path | None:
    raw = str(rec.get("path") or "").strip()
    if not raw:
        return None
    p = Path(raw)
    candidates = [
        p if p.is_absolute() else root / p,
        root / "clips" / Path(raw).name,
        root / "takes" / Path(raw).name,
    ]
    for c in candidates:
        if c.is_file() and c.stat().st_size > 0:
            return c
    return None


def _approved_clip_paths(
    root: Path,
    spec: dict[str, Any],
    man: dict[str, Any],
    *,
    allow_candidate: bool = False,
) -> list[tuple[str, Path]]:
    clips = man.get("clips") if isinstance(man.get("clips"), dict) else {}
    ordered: list[tuple[str, Path]] = []
    for sh in _flatten_shots(spec):
        sid = str(sh.get("id") or "").strip()
        if not sid:
            continue
        rec = clips.get(sid)
        if not isinstance(rec, dict):
            raise H3ShipNativeError(f"missing clip record for {sid}")
        status = str(rec.get("status") or "").lower()
        allowed = {"approved", "candidate"} if allow_candidate else {"approved"}
        if status not in allowed:
            raise H3ShipNativeError(
                f"shot {sid} clip status={status!r} not usable "
                f"(need {'|'.join(sorted(allowed))})"
            )
        path = _clip_path(root, rec)
        if path is None:
            raise H3ShipNativeError(f"shot {sid}: clip path missing on disk: {rec.get('path')}")
        ordered.append((sid, path))
    if not ordered:
        raise H3ShipNativeError("no shots/clips to concat")
    return ordered


def _ffprobe_has_audio(path: Path) -> bool:
    try:
        r = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "a",
                "-show_entries",
                "stream=codec_type",
                "-of",
                "csv=p=0",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        return "audio" in (r.stdout or "").lower()
    except (OSError, subprocess.TimeoutExpired):
        return False


def _hard_concat(parts: list[Path], out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    lst = out.parent / f".ship_native_concat_{out.stem}.txt"
    # Escape single quotes for concat demuxer
    lines = []
    for p in parts:
        s = str(p.resolve()).replace("'", r"'\''")
        lines.append(f"file '{s}'\n")
    lst.write_text("".join(lines), encoding="utf-8")
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(lst),
        "-c",
        "copy",
        str(out),
    ]
    # copy may fail if codecs differ; re-encode fallback
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=600, check=False)
    if r.returncode == 0 and out.is_file() and out.stat().st_size > 0:
        try:
            lst.unlink(missing_ok=True)
        except OSError:
            pass
        return
    cmd_re = [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(lst),
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        str(out),
    ]
    r2 = subprocess.run(cmd_re, capture_output=True, text=True, timeout=900, check=False)
    try:
        lst.unlink(missing_ok=True)
    except OSError:
        pass
    if r2.returncode != 0 or not out.is_file() or out.stat().st_size <= 0:
        err = (r2.stderr or r.stderr or "")[-800:]
        raise H3ShipNativeError(f"ffmpeg concat failed: {err}")


def check_duration_vs_target(
    root: Path,
    spec: dict[str, Any],
    parts: list[Path],
) -> dict[str, Any]:
    from plan.duration_target import check_duration_target
    from media_duration import MediaDurationError, probe_duration_sec

    media_sum = 0.0
    for p in parts:
        try:
            media_sum += probe_duration_sec(p, label=p.name)
        except MediaDurationError:
            continue
    return check_duration_target(spec, media_sum_sec=media_sum)


def ship_native(
    root: Path | str,
    *,
    out_path: Path | str | None = None,
    allow_candidate: bool = False,
    dry_run: bool = False,
    sample_audio: int = 3,
) -> dict[str, Any]:
    """Build H3-native plate from approved (or candidate) clips."""
    root_p = Path(root).expanduser().resolve()
    spec = read_json(root_p / "film-spec.json") or {}
    man = read_json(root_p / "manifest.json") or {}
    ordered = _approved_clip_paths(
        root_p, spec, man, allow_candidate=allow_candidate
    )
    parts = [p for _, p in ordered]
    shot_ids = [s for s, _ in ordered]

    audio_flags = [_ffprobe_has_audio(p) for p in parts]
    with_audio = sum(1 for a in audio_flags if a)
    sample_n = max(0, min(int(sample_audio), len(parts)))
    sample_notes = [
        {"shot_id": shot_ids[i], "path": str(parts[i]), "has_audio_stream": audio_flags[i]}
        for i in range(sample_n)
    ]

    dur_rep = check_duration_vs_target(root_p, spec, parts)

    out = Path(out_path).expanduser().resolve() if out_path else (
        root_p / "out" / "film_native_h3.mp4"
    )
    report: dict[str, Any] = {
        "schema_version": 1,
        "kind": "h3_ship_native",
        "at": utc_now(),
        "root": str(root_p),
        "ok": False,
        "delivery_class": "OFFICIAL_FINAL_PLATE",
        "master_lock": False,
        "shot_ids": shot_ids,
        "clip_count": len(parts),
        "clips_with_audio_stream": with_audio,
        "audio_sample": sample_notes,
        "out": str(out),
        "duration_target": dur_rep,
        "notes": [
            "native ship preserves clip aac when present; aac≠intelligible Mandarin",
            "not master_lock; run gate-auto + review-final for formal master",
            "optional: aifilm final --skip-canonical-truth for Edge+hardburn path",
        ],
        "next": list(dur_rep.get("next") or []),
    }

    if dry_run:
        report["ok"] = True
        report["dry_run"] = True
        report["message"] = f"dry: would concat {len(parts)} clips → {out}"
        write_json(root_p / "receipts" / "h3-ship-native.json", report)
        return report

    if os.environ.get("AIFILM_SKIP_H3_SHIP_NATIVE", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }:
        raise H3ShipNativeError("AIFILM_SKIP_H3_SHIP_NATIVE=1")

    _hard_concat(parts, out)
    if not out.is_file() or out.stat().st_size <= 0:
        raise H3ShipNativeError(f"output missing after concat: {out}")

    # optional copy to film_final only if user asks via env (never silent)
    if os.environ.get("AIFILM_H3_SHIP_AS_FILM_FINAL", "").strip() in {"1", "true", "yes"}:
        dest = root_p / "out" / "film_final.mp4"
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(out, dest)
        report["also_copied_to"] = str(dest)

    report["ok"] = True
    report["out_bytes"] = out.stat().st_size
    report["message"] = (
        f"shipped {len(parts)} clips ({with_audio} with audio stream) → {out} "
        f"[{report['delivery_class']}]"
    )
    if not dur_rep.get("ok"):
        report["notes"].append(
            f"duration honesty not ok: {dur_rep.get('message')} — plate still written"
        )
        report["next"] = list(dict.fromkeys((report.get("next") or []) + (dur_rep.get("next") or [])))

    write_json(root_p / "receipts" / "h3-ship-native.json", report)
    # Align with plate vs master honesty when official-final helper exists
    try:
        from final.delivery_class import write_plate_report  # type: ignore

        write_plate_report(
            root_p,
            status="OFFICIAL_FINAL_PLATE",
            reason="h3_ship_native",
            path=str(out),
        )
    except Exception:
        pass
    return report

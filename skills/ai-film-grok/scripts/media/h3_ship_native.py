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
from util.errors import FilmError

try:
    from final.native_audio import (
        FILM_NATIVE_SPEECH_BROKEN_BASENAME,
        FILM_NATIVE_STABLE_BASENAME,
        NATIVE_LIGHT_AF_FILTER,
    )
except ImportError:  # pragma: no cover — flat scripts path
    from native_audio import (  # type: ignore
        FILM_NATIVE_SPEECH_BROKEN_BASENAME,
        FILM_NATIVE_STABLE_BASENAME,
        NATIVE_LIGHT_AF_FILTER,
    )


class H3ShipNativeError(FilmError):
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


def _mean_volume_db(path: Path) -> float | None:
    """Best-effort volumedetect via core.media_ops (single implementation)."""
    try:
        from core.media_ops import probe_native_audio_mean_volume

        return probe_native_audio_mean_volume(path, timeout=60.0)
    except Exception:
        return None


def sample_native_audio_audit(
    shot_ids: list[str],
    parts: list[Path],
    *,
    sample_n: int = 3,
    silence_db: float = -45.0,
    mandarin_hard: bool | None = None,
) -> dict[str, Any]:
    """Q5.2 + S1.3 soft native-audio honesty: stream + mean_volume on head samples.

    Always notes aac≠可懂中文. Optional hard: env ``AIFILM_NATIVE_AUDIO_MANDARIN_HARD=1``
    promotes stream/quiet failures to severity hard (still not ASR).
    """
    n = max(0, min(int(sample_n), len(parts)))
    rows: list[dict[str, Any]] = []
    silentish = 0
    no_stream = 0
    for i in range(n):
        has = _ffprobe_has_audio(parts[i])
        mean = _mean_volume_db(parts[i]) if has else None
        if not has:
            no_stream += 1
        if mean is not None and mean < silence_db:
            silentish += 1
        rows.append(
            {
                "shot_id": shot_ids[i],
                "path": str(parts[i]),
                "has_audio_stream": has,
                "mean_volume_db": mean,
                "likely_silent": bool(mean is not None and mean < silence_db),
            }
        )
    codes: list[str] = []
    if no_stream == n and n > 0:
        codes.append("NATIVE_AUDIO_NO_STREAM_SAMPLE")
    if silentish >= max(1, n // 2) and n > 0:
        codes.append("NATIVE_AUDIO_QUIET_SAMPLE")
    # S1.3 · always soft-remind Mandarin unverified when any sample has a stream
    if n > 0 and no_stream < n:
        codes.append("NATIVE_AUDIO_MANDARIN_UNVERIFIED")
    if mandarin_hard is None:
        mandarin_hard = os.environ.get("AIFILM_NATIVE_AUDIO_MANDARIN_HARD", "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
    stream_fail = {
        c
        for c in codes
        if c in {"NATIVE_AUDIO_NO_STREAM_SAMPLE", "NATIVE_AUDIO_QUIET_SAMPLE"}
    }
    if mandarin_hard and stream_fail:
        severity = "hard"
        codes.append("NATIVE_AUDIO_MANDARIN_HARD")
        ok = False
    elif codes:
        severity = "soft"
        ok = True  # soft codes do not fail ship-native by default
    else:
        severity = "ok"
        ok = True
    next_hint = [
        "aac stream ≠ intelligible Mandarin — spot-listen before claiming native dialogue",
        "fallback: Edge TTS ADR clock + ship_hardburn captions via aifilm final",
    ]
    if mandarin_hard:
        next_hint.append(
            "AIFILM_NATIVE_AUDIO_MANDARIN_HARD=1: quiet/no-stream samples fail closed"
        )
    return {
        "sample_n": n,
        "rows": rows,
        "codes": codes,
        "ok": ok,
        "severity": severity,
        "mandarin_hard": bool(mandarin_hard),
        "next": next_hint if codes else [],
        "note": "volumedetect only; not ASR. aac≠中文对白清晰. checklist: spot-listen sample rows.",
        "listen_checklist": [
            "抽听 sample rows 是否有可懂中文口白（非氛围/外语噪声）",
            "无中文可懂 → Edge ADR + ship_hardburn，勿声称 native dialogue",
        ],
    }


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


def _env_flag_on(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def apply_native_light_af_filter(
    src: Path,
    dst: Path,
    *,
    af_filter: str | None = None,
) -> dict[str, Any]:
    """Re-encode audio with NATIVE_LIGHT_AF_FILTER; copy video.

    P0 · no agate / dual arnndn — uses the single IRON string only.
    Returns a small receipt dict (ok / filter / paths / error).
    """
    filt = (af_filter or NATIVE_LIGHT_AF_FILTER).strip()
    if "agate" in filt or "arnndn" in filt:
        raise H3ShipNativeError(
            "native light filter must not contain agate/arnndn — use NATIVE_LIGHT_AF_FILTER"
        )
    src = Path(src)
    dst = Path(dst)
    if not src.is_file() or src.stat().st_size <= 0:
        raise H3ShipNativeError(f"light-process source missing: {src}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    # Write to temp then replace so src==dst is safe
    tmp = dst.parent / f".{dst.stem}_light_af{dst.suffix}"
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(src),
        "-c:v",
        "copy",
        "-af",
        filt,
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-movflags",
        "+faststart",
        str(tmp),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=900, check=False)
    if r.returncode != 0 or not tmp.is_file() or tmp.stat().st_size <= 0:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        err = (r.stderr or "")[-800:]
        raise H3ShipNativeError(f"native light af filter failed: {err}")
    try:
        tmp.replace(dst)
    except OSError:
        import shutil as _sh

        _sh.copy2(tmp, dst)
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
    return {
        "ok": True,
        "filter": filt,
        "src": str(src),
        "out": str(dst),
        "bytes": dst.stat().st_size if dst.is_file() else 0,
        "forbid": ["agate", "arnndn", "dual_arnndn"],
    }


def check_duration_vs_target(
    root: Path,
    spec: dict[str, Any],
    parts: list[Path],
) -> dict[str, Any]:
    from media_duration import MediaDurationError, probe_duration_sec
    from plan.duration_target import check_duration_target

    media_sum = 0.0
    for p in parts:
        try:
            media_sum += probe_duration_sec(p, label=p.name)
        except MediaDurationError:
            continue
    return check_duration_target(spec, media_sum_sec=media_sum)


def _stage2_final_cmd(
    root: Path,
    *,
    caption: str | None,
    music_mood: str | None,
) -> str:
    """Exact next command for hardburn/BGM after native concat (S1.1 honesty)."""
    cap = (caption or "ship_hardburn").strip() or "ship_hardburn"
    if cap in {"hardburn", "ship", "on", "true", "1"}:
        cap = "ship_hardburn"
    mood = (music_mood or "rnb").strip() or "rnb"
    return (
        f'aifilm final --root "{root}" --skip-canonical-truth '
        f"--post-engine ffmpeg --tts-backend edge --music-mood {mood} "
        f"--caption-path {cap}"
    )


def ship_native(
    root: Path | str,
    *,
    out_path: Path | str | None = None,
    allow_candidate: bool = False,
    dry_run: bool = False,
    sample_audio: int = 3,
    caption: str | None = None,
    music_mood: str | None = None,
    light_process: bool | None = None,
) -> dict[str, Any]:
    """Build H3-native plate from approved (or candidate) clips.

    S1.1: optional ``caption`` / ``music_mood`` only attach stage-2 final
    command in the receipt — this path never silently claims hardburn/BGM.

    ``light_process``: after concat, re-encode audio with
    ``NATIVE_LIGHT_AF_FILTER`` (video copy). Default off for speed; enable via
    arg or env ``AIFILM_H3_SHIP_LIGHT_PROCESS=1``. Never agate/dual-arnndn.
    """
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
    audio_audit = sample_native_audio_audit(
        shot_ids, parts, sample_n=int(sample_audio or 3)
    )

    dur_rep = check_duration_vs_target(root_p, spec, parts)

    # P0 deliverable name: film_native_stable (hard-defaults · 禁 film_watchable 冒充)
    out = Path(out_path).expanduser().resolve() if out_path else (
        root_p / "out" / FILM_NATIVE_STABLE_BASENAME
    )
    if light_process is None:
        light_process = _env_flag_on("AIFILM_H3_SHIP_LIGHT_PROCESS")
    else:
        light_process = bool(light_process)
    wants_stage2 = bool(
        (caption and str(caption).strip().lower() not in {"", "none", "off", "0"})
        or (music_mood and str(music_mood).strip().lower() not in {"", "none", "off", "0"})
    )
    stage2_cmd = _stage2_final_cmd(
        root_p,
        caption=caption if wants_stage2 else "ship_hardburn",
        music_mood=music_mood if wants_stage2 else "rnb",
    )
    stage2 = {
        "required_for_captions_or_bgm": True,
        "requested": wants_stage2,
        "caption": caption,
        "music_mood": music_mood,
        "concat_includes_hardburn": False,
        "concat_includes_bgm": False,
        "command": stage2_cmd,
        "note": (
            "ship-native = concat plate only; hardburn/rnb is stage-2 via aifilm final "
            "(not auto-run here — avoids false master)"
        ),
    }
    # S1.3 · soft Mandarin intelligibility checklist (aac ≠ 可懂中文)
    mandarin_soft = {
        "schema_version": 1,
        "kind": "mandarin_intelligibility_soft",
        "severity": "soft",
        "ok": True,
        "codes": [],
        "checklist": [
            "sample ≥3 dialogue clips by ear (or spot-check mean_volume not silence)",
            "confirm speech is Mandarin-intelligible (not FX / foreign noise only)",
            "if unintelligible: re-I2V with dialogue energy or ADR Edge clock only",
            "hard ASR gate deferred — set AIFILM_MANDARIN_HARD=1 later if product wants",
        ],
        "clips_with_audio_stream": with_audio,
        "clip_count": len(parts),
        "note": "soft only; does not fail ship-native",
    }
    if with_audio == 0 and parts:
        mandarin_soft["codes"].append("NATIVE_AUDIO_STREAM_MISSING_SOFT")
        mandarin_soft["ok"] = False
    elif with_audio < max(1, len(parts) // 3):
        mandarin_soft["codes"].append("NATIVE_AUDIO_SPARSE_SOFT")

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
        "audio_sample": audio_audit.get("rows"),
        "native_audio_audit": audio_audit,
        "mandarin_intelligibility": mandarin_soft,
        # H3 原声轻处理 IRON — concat keeps aac; optional re-encode uses this filter only
        "native_light_af_filter": NATIVE_LIGHT_AF_FILTER,
        "native_light_policy": {
            "default": "copy_then_optional_light",
            "light_process_requested": bool(light_process),
            "light_process_env": "AIFILM_H3_SHIP_LIGHT_PROCESS=1",
            "forbid_default": ["agate", "arnndn", "dual_arnndn"],
            "stable_basename": FILM_NATIVE_STABLE_BASENAME,
            "broken_basename": FILM_NATIVE_SPEECH_BROKEN_BASENAME,
            "note": (
                "concat uses -c copy. When light_process is on, post-concat audio "
                "re-encode uses native_light_af_filter only (no agate/dual-arnndn)."
            ),
        },
        "out": str(out),
        "duration_target": dur_rep,
        "stage2": stage2,
        "notes": [
            "native ship preserves clip aac when present; aac≠intelligible Mandarin",
            "OFFICIAL_FINAL_PLATE only — concat does not hardburn or mix rnb",
            "not master_lock; formal master = gate-auto green + review-final",
            f"stage-2 captions/BGM: {stage2_cmd}",
            "S1.3 mandarin checklist soft in receipts (not ASR hard)",
            f"light filter (if re-encode): {NATIVE_LIGHT_AF_FILTER}",
            "forbid default agate / dual arnndn on native dialogue (P0 2026-08-07)",
        ],
        "next": list(
            dict.fromkeys(
                list(dur_rep.get("next") or [])
                + list(audio_audit.get("next") or [])
                + [
                    stage2_cmd + "  # plate→hardburn/BGM stage-2",
                    f'aifilm gate-auto --root "{root_p}"',
                    "spot-listen sample clips for Mandarin intelligibility (soft)",
                ]
            )
        ),
    }
    if wants_stage2:
        report["notes"].append(
            "caption/music-mood flags recorded for stage-2 only — "
            "this receipt is still OFFICIAL_FINAL_PLATE without burned subs/BGM"
        )

    if dry_run:
        report["ok"] = True
        report["dry_run"] = True
        report["message"] = (
            f"dry: would concat {len(parts)} clips → {out}"
            + (" + light af" if light_process else "")
        )
        report["native_light_policy"]["would_apply_light_af"] = bool(light_process)
        write_json(root_p / "receipts" / "h3-ship-native.json", report)
        return report

    try:
        from core.skip_audit import skip_flag

        if skip_flag(
            "AIFILM_SKIP_H3_SHIP_NATIVE",
            origin="env",
            film_root=root_p,
            call_site="h3_ship_native",
        ):
            raise H3ShipNativeError("AIFILM_SKIP_H3_SHIP_NATIVE=1")
    except H3ShipNativeError:
        raise
    except Exception:
        if os.environ.get("AIFILM_SKIP_H3_SHIP_NATIVE", "").strip().lower() in {
            "1",
            "true",
            "yes",
        }:
            raise H3ShipNativeError("AIFILM_SKIP_H3_SHIP_NATIVE=1")

    _hard_concat(parts, out)
    if not out.is_file() or out.stat().st_size <= 0:
        raise H3ShipNativeError(f"output missing after concat: {out}")

    if light_process:
        try:
            light_rep = apply_native_light_af_filter(out, out)
            report["native_light_applied"] = light_rep
            report["notes"].append(
                f"post-concat light af applied: {light_rep.get('filter')}"
            )
        except H3ShipNativeError as exc:
            report["native_light_applied"] = {"ok": False, "error": str(exc)[:300]}
            report.setdefault("honest_limits", []).append(
                f"light_af_failed:{str(exc)[:120]}"
            )
            report["notes"].append(
                "light af failed — plate kept as concat copy (PARTIAL honesty)"
            )

    # Legacy closeout path alias (film_native_h3) — same plate, not a second master
    try:
        legacy = root_p / "out" / "film_native_h3.mp4"
        if out.resolve() != legacy.resolve():
            legacy.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(out, legacy)
            report["legacy_alias"] = str(legacy)
    except OSError as exc:
        report.setdefault("honest_limits", []).append(f"legacy_alias_failed:{exc}")

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
    # Align with plate vs master honesty (OFFICIAL_FINAL_PLATE; never master_lock)
    try:
        from final.delivery_class import (
            classify_official_final,
            write_official_final_report,
        )

        official = classify_official_final(
            skip_preflight=True,
            final_complete=False,
            gate_auto_ok=None,
        )
        official["status"] = "OFFICIAL_FINAL_PLATE"
        official["partial"] = True
        official["reason"] = "h3_ship_native"
        official["path"] = str(out)
        official["master_lock"] = False
        write_official_final_report(root_p, official)
    except Exception as exc:  # noqa: BLE001
        report.setdefault("honest_limits", []).append(
            f"plate_report_write_failed:{type(exc).__name__}:{str(exc)[:100]}"
        )
    return report

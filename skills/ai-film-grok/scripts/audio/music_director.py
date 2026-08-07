"""Music Director — H3 native voice + BGM plan (draft / normalize / apply / review).

Single source of truth: ``audio/music-director-plan.json``.

- BGM: mood / energy / duck_db / mute_bed per shot (feeds music_cue overlay).
- Native voice: gain, peak_fix, mute_windows (plate-local), mute_entire / silence lane.
- Wrong dialogue v1 = **audio mute** (picture unchanged). Picture cuts stay on editor_cut.
"""

from __future__ import annotations

import json
import tempfile
import wave
from copy import deepcopy
from pathlib import Path
from typing import Any

import numpy as np

from util import require_json as read_json
from util import sha256_file, utc_now, write_json
from util.errors import FilmError

SCHEMA = "aifilm-music-director-plan-v1"
PLAN_REL = Path("audio") / "music-director-plan.json"
APPLY_RECEIPT_REL = Path("receipts") / "music-director-apply.json"
DIRECTED_DIR_REL = Path("audio") / "native_directed"
_LANES = frozenset({"native", "post_tts", "silence"})
_PEAK_FIX = frozenset({"auto", "off"})
_PROCESS = frozenset({"light", "none"})


class MusicDirectorError(FilmError):
    """Plan / apply failures for the music director desk."""


def plan_path(root: Path) -> Path:
    return Path(root).expanduser().resolve() / PLAN_REL


def apply_receipt_path(root: Path) -> Path:
    return Path(root).expanduser().resolve() / APPLY_RECEIPT_REL


def directed_dir(root: Path) -> Path:
    return Path(root).expanduser().resolve() / DIRECTED_DIR_REL


def directed_stem_path(root: Path, shot_id: str) -> Path:
    return directed_dir(root) / f"{shot_id}.wav"


def _flatten_shots(spec: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not isinstance(spec, dict):
        return out
    scenes = spec.get("scenes")
    if isinstance(scenes, list) and scenes:
        for scene in scenes:
            if not isinstance(scene, dict):
                continue
            for shot in scene.get("shots") or []:
                if isinstance(shot, dict) and shot.get("id") is not None:
                    out.append(shot)
        if out:
            return out
    for shot in spec.get("shots") or []:
        if isinstance(shot, dict) and shot.get("id") is not None:
            out.append(shot)
    return out


def _load_spec(root: Path) -> dict[str, Any]:
    path = Path(root).expanduser().resolve() / "film-spec.json"
    if not path.is_file():
        raise MusicDirectorError(f"missing film-spec.json under {root}")
    data = read_json(path)
    if not isinstance(data, dict):
        raise MusicDirectorError("film-spec.json must be an object")
    return data


def _audio_policy(spec: dict[str, Any]) -> str:
    ap = spec.get("audio_policy")
    h3 = spec.get("h3") if isinstance(spec.get("h3"), dict) else {}
    if isinstance(ap, dict):
        return str(ap.get("mode") or ap.get("audio_policy") or h3.get("audio_policy") or "prefer_native")
    return str(ap or h3.get("audio_policy") or "prefer_native")


def _default_mood(spec: dict[str, Any]) -> str:
    mood = str(spec.get("bgm_mood") or (spec.get("sound") or {}).get("mood") or "rnb").strip().lower()
    return mood if mood in {"rnb", "dark", "ambient", "warm", "playful"} else "rnb"


def _shot_lane(shot: dict[str, Any]) -> str:
    lane = str(shot.get("dialogue_audio_lane") or "").strip().lower()
    if lane in _LANES:
        return lane
    # H3 native desk default for spoken; silence for non-spoken
    spoken = bool(
        str(shot.get("spoken_text") or shot.get("nar") or shot.get("dialogue") or "").strip()
    )
    return "native" if spoken else "silence"


def _bgm_row_from_shot(shot: dict[str, Any], *, default_mood: str) -> dict[str, Any]:
    try:
        from music_cue import compile_music_cue

        cue = compile_music_cue(shot, default_mood=default_mood)
    except Exception:
        cue = {
            "mood": default_mood,
            "energy": 0.55,
            "duck_db": -3.0 if str(shot.get("nar") or shot.get("dialogue") or "").strip() else 0.0,
        }
    return {
        "shot_id": str(shot.get("id")),
        "mood": str(cue.get("mood") or default_mood),
        "energy": float(cue.get("energy", 0.55)),
        "duck_db": float(cue.get("duck_db", 0.0)),
        "mute_bed": False,
    }


def draft_plan(
    root: Path | None = None,
    *,
    spec: dict[str, Any] | None = None,
    director_notes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a default music-director plan from film-spec (+ optional notes)."""
    if spec is None:
        if root is None:
            raise MusicDirectorError("draft_plan requires root or spec")
        spec = _load_spec(root)
    shots = _flatten_shots(spec)
    mood = _default_mood(spec)
    bgm_shots = [_bgm_row_from_shot(s, default_mood=mood) for s in shots]
    voice_shots: list[dict[str, Any]] = []
    for shot in shots:
        sid = str(shot.get("id"))
        lane = _shot_lane(shot)
        voice_shots.append(
            {
                "shot_id": sid,
                "lane": lane,
                "gain": 1.0,
                "peak_fix": "auto" if lane == "native" else "off",
                "mute_windows": [],
                "mute_entire": lane == "silence",
                "reason": "draft_default",
                "caption_policy": "keep_chinese",
            }
        )
    notes = ""
    if isinstance(director_notes, dict):
        notes = str(director_notes.get("music_director") or director_notes.get("notes") or "")
    plan = {
        "schema": SCHEMA,
        "audio_policy": _audio_policy(spec),
        "source": "draft",
        "created_at": utc_now(),
        "bgm": {
            "default_mood": mood,
            "global_gain": 0.35,
            "shots": bgm_shots,
        },
        "native_voice": {
            "default_process": "light",
            "peak_policy": {"true_peak_dbtp": -1.5, "limiter": 0.95},
            "shots": voice_shots,
        },
        "review": {
            "listen_points_sec": [],
            "notes": notes,
        },
    }
    return normalize_plan(plan)


def normalize_plan(plan: dict[str, Any] | None) -> dict[str, Any]:
    """Validate and normalize a music-director plan (fail-closed on bad windows)."""
    if not isinstance(plan, dict):
        raise MusicDirectorError("plan must be an object")
    out = deepcopy(plan)
    out["schema"] = SCHEMA
    policy = str(out.get("audio_policy") or "prefer_native").strip() or "prefer_native"
    out["audio_policy"] = policy
    out["source"] = str(out.get("source") or "director").strip() or "director"

    bgm_raw = out.get("bgm") if isinstance(out.get("bgm"), dict) else {}
    mood = str(bgm_raw.get("default_mood") or "rnb").strip().lower()
    if mood not in {"rnb", "dark", "ambient", "warm", "playful"}:
        raise MusicDirectorError(f"bgm.default_mood invalid: {mood}")
    try:
        global_gain = float(bgm_raw.get("global_gain", 0.35))
    except (TypeError, ValueError) as exc:
        raise MusicDirectorError("bgm.global_gain must be numeric") from exc
    if not 0.0 <= global_gain <= 1.0:
        raise MusicDirectorError("bgm.global_gain must be between 0 and 1")
    bgm_shots: list[dict[str, Any]] = []
    for row in bgm_raw.get("shots") or []:
        if not isinstance(row, dict):
            raise MusicDirectorError("bgm.shots entries must be objects")
        sid = str(row.get("shot_id") or "").strip()
        if not sid:
            raise MusicDirectorError("bgm.shots[].shot_id required")
        try:
            energy = float(row.get("energy", 0.55))
            duck_db = float(row.get("duck_db", 0.0))
        except (TypeError, ValueError) as exc:
            raise MusicDirectorError(f"bgm shot {sid}: energy/duck_db numeric") from exc
        if not 0.0 <= energy <= 1.0:
            raise MusicDirectorError(f"bgm shot {sid}: energy must be 0..1")
        if not -18.0 <= duck_db <= 0.0:
            raise MusicDirectorError(f"bgm shot {sid}: duck_db must be -18..0")
        bgm_shots.append(
            {
                "shot_id": sid,
                "mood": str(row.get("mood") or mood).strip().lower(),
                "energy": round(energy, 4),
                "duck_db": round(duck_db, 2),
                "mute_bed": bool(row.get("mute_bed", False)),
            }
        )
    out["bgm"] = {
        "default_mood": mood,
        "global_gain": round(global_gain, 4),
        "shots": bgm_shots,
    }

    nv_raw = out.get("native_voice") if isinstance(out.get("native_voice"), dict) else {}
    process = str(nv_raw.get("default_process") or "light").strip().lower()
    if process not in _PROCESS:
        raise MusicDirectorError(f"native_voice.default_process must be one of {sorted(_PROCESS)}")
    peak_raw = nv_raw.get("peak_policy") if isinstance(nv_raw.get("peak_policy"), dict) else {}
    try:
        true_peak = float(peak_raw.get("true_peak_dbtp", -1.5))
        limiter = float(peak_raw.get("limiter", 0.95))
    except (TypeError, ValueError) as exc:
        raise MusicDirectorError("peak_policy true_peak_dbtp/limiter must be numeric") from exc
    if not -6.0 <= true_peak <= 0.0:
        raise MusicDirectorError("true_peak_dbtp must be between -6 and 0")
    if not 0.5 <= limiter <= 1.0:
        raise MusicDirectorError("limiter must be between 0.5 and 1.0")

    voice_shots: list[dict[str, Any]] = []
    for row in nv_raw.get("shots") or []:
        if not isinstance(row, dict):
            raise MusicDirectorError("native_voice.shots entries must be objects")
        sid = str(row.get("shot_id") or "").strip()
        if not sid:
            raise MusicDirectorError("native_voice.shots[].shot_id required")
        lane = str(row.get("lane") or "native").strip().lower()
        if lane not in _LANES:
            raise MusicDirectorError(f"shot {sid}: lane must be native|post_tts|silence")
        mute_entire = bool(row.get("mute_entire", False))
        if mute_entire:
            lane = "silence"
        try:
            gain = float(row.get("gain", 1.0))
        except (TypeError, ValueError) as exc:
            raise MusicDirectorError(f"shot {sid}: gain must be numeric") from exc
        if not 0.0 <= gain <= 2.0:
            raise MusicDirectorError(f"shot {sid}: gain must be 0..2")
        peak_fix = str(row.get("peak_fix") or ("auto" if lane == "native" else "off")).strip().lower()
        if peak_fix not in _PEAK_FIX:
            raise MusicDirectorError(f"shot {sid}: peak_fix must be auto|off")
        windows: list[dict[str, Any]] = []
        for win in row.get("mute_windows") or []:
            if not isinstance(win, dict):
                raise MusicDirectorError(f"shot {sid}: mute_windows entries must be objects")
            try:
                start = float(win.get("start_sec"))
                end = float(win.get("end_sec"))
            except (TypeError, ValueError) as exc:
                raise MusicDirectorError(f"shot {sid}: mute window needs start_sec/end_sec") from exc
            if start < 0 or end <= start:
                raise MusicDirectorError(
                    f"shot {sid}: mute window invalid start={start} end={end} (plate-local, end>start)"
                )
            windows.append(
                {
                    "start_sec": round(start, 4),
                    "end_sec": round(end, 4),
                    "reason": str(win.get("reason") or "wrong_line"),
                    "source": str(win.get("source") or "director"),
                }
            )
        voice_shots.append(
            {
                "shot_id": sid,
                "lane": lane,
                "gain": round(gain, 4),
                "peak_fix": peak_fix,
                "mute_windows": windows,
                "mute_entire": mute_entire or lane == "silence",
                "reason": str(row.get("reason") or ""),
                "caption_policy": str(row.get("caption_policy") or "keep_chinese"),
            }
        )
    out["native_voice"] = {
        "default_process": process,
        "peak_policy": {
            "true_peak_dbtp": round(true_peak, 3),
            "limiter": round(limiter, 3),
        },
        "shots": voice_shots,
    }
    rev = out.get("review") if isinstance(out.get("review"), dict) else {}
    points: list[float] = []
    for p in rev.get("listen_points_sec") or []:
        try:
            points.append(round(float(p), 3))
        except (TypeError, ValueError) as exc:
            raise MusicDirectorError("review.listen_points_sec must be numeric") from exc
    out["review"] = {
        "listen_points_sec": points,
        "notes": str(rev.get("notes") or ""),
    }
    return out


def merge_director_overrides(plan: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    """Deep-merge director overrides; human fields win. Re-normalize."""
    base = normalize_plan(plan)
    if not isinstance(overrides, dict):
        raise MusicDirectorError("overrides must be an object")
    merged = deepcopy(base)
    if "audio_policy" in overrides:
        merged["audio_policy"] = overrides["audio_policy"]
    if "source" in overrides:
        merged["source"] = overrides["source"]
    if isinstance(overrides.get("bgm"), dict):
        bgm = merged["bgm"]
        ob = overrides["bgm"]
        for key in ("default_mood", "global_gain"):
            if key in ob:
                bgm[key] = ob[key]
        if isinstance(ob.get("shots"), list):
            by_id = {row["shot_id"]: row for row in bgm["shots"]}
            for row in ob["shots"]:
                if not isinstance(row, dict):
                    continue
                sid = str(row.get("shot_id") or "")
                if not sid:
                    continue
                if sid in by_id:
                    by_id[sid] = {**by_id[sid], **row, "shot_id": sid}
                else:
                    by_id[sid] = row
            bgm["shots"] = list(by_id.values())
    if isinstance(overrides.get("native_voice"), dict):
        nv = merged["native_voice"]
        on = overrides["native_voice"]
        if "default_process" in on:
            nv["default_process"] = on["default_process"]
        if isinstance(on.get("peak_policy"), dict):
            nv["peak_policy"] = {**nv.get("peak_policy", {}), **on["peak_policy"]}
        if isinstance(on.get("shots"), list):
            by_id = {row["shot_id"]: row for row in nv["shots"]}
            for row in on["shots"]:
                if not isinstance(row, dict):
                    continue
                sid = str(row.get("shot_id") or "")
                if not sid:
                    continue
                if sid in by_id:
                    prev = by_id[sid]
                    merged_row = {**prev, **row, "shot_id": sid}
                    if "mute_windows" in row:
                        merged_row["mute_windows"] = row["mute_windows"]
                    by_id[sid] = merged_row
                else:
                    by_id[sid] = row
            nv["shots"] = list(by_id.values())
    if isinstance(overrides.get("review"), dict):
        merged["review"] = {**merged.get("review", {}), **overrides["review"]}
    merged["source"] = str(overrides.get("source") or "director")
    return normalize_plan(merged)


def load_plan(root: Path) -> dict[str, Any] | None:
    path = plan_path(root)
    if not path.is_file():
        return None
    data = read_json(path)
    if not isinstance(data, dict):
        raise MusicDirectorError(f"invalid plan at {path}")
    return normalize_plan(data)


def save_plan(root: Path, plan: dict[str, Any]) -> Path:
    path = plan_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized = normalize_plan(plan)
    write_json(path, normalized)
    return path


def bgm_overlay_for_shot(plan: dict[str, Any], shot_id: str) -> dict[str, Any] | None:
    """Return BGM row for shot_id if present (for music_cue overlay)."""
    plan = normalize_plan(plan)
    for row in plan["bgm"]["shots"]:
        if row["shot_id"] == shot_id:
            return row
    return None


def apply_bgm_to_shots(shots: list[dict[str, Any]], plan: dict[str, Any]) -> int:
    """Mutate shot.music_cue from plan BGM rows. Returns patched count."""
    plan = normalize_plan(plan)
    by_id = {row["shot_id"]: row for row in plan["bgm"]["shots"]}
    n = 0
    for shot in shots:
        if not isinstance(shot, dict):
            continue
        sid = str(shot.get("id") or "")
        row = by_id.get(sid)
        if not row:
            continue
        cue = dict(shot.get("music_cue") or {}) if isinstance(shot.get("music_cue"), dict) else {}
        cue["mood"] = row["mood"]
        cue["energy"] = row["energy"]
        cue["duck_db"] = -18.0 if row.get("mute_bed") else row["duck_db"]
        if row.get("mute_bed"):
            cue["stem_profile"] = "silence"
        shot["music_cue"] = cue
        n += 1
    return n


def discover_native_source(root: Path, shot_id: str) -> Path | None:
    """Find registered or conventional native audio for one shot.

    Order: audio/native → native/ → manifest.native_audio → clips media.
    """
    root = Path(root).expanduser().resolve()
    candidates: list[Path] = []
    for folder in (root / "audio" / "native", root / "native", root / "clips"):
        for ext in (".wav", ".mp3", ".m4a", ".aac", ".flac", ".mp4", ".mov", ".webm"):
            candidates.append(folder / f"{shot_id}{ext}")
    for path in candidates:
        if path.is_file():
            return path
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        return None
    man = read_json(manifest_path)
    if not isinstance(man, dict):
        return None
    clips = man.get("clips") or {}
    rec = clips.get(shot_id) if isinstance(clips, dict) else None
    if not isinstance(rec, dict):
        return None

    def _resolve_rel(rel: str) -> Path | None:
        rel = str(rel)
        if Path(rel).is_absolute() and Path(rel).is_file():
            return Path(rel)
        for base in (
            root / "audio" / "native",
            root / "native",
            root / "clips",
            root / "audio",
            root,
        ):
            cand = (base / rel).resolve()
            try:
                if cand.is_file() and str(cand).startswith(str(root)):
                    return cand
            except OSError:
                continue
        return None

    na = rec.get("native_audio")
    if isinstance(na, dict) and na.get("path"):
        hit = _resolve_rel(str(na["path"]))
        if hit is not None:
            return hit
    for key in ("path", "file", "clip", "video", "mp4"):
        if rec.get(key):
            hit = _resolve_rel(str(rec[key]))
            if hit is not None:
                return hit
    return None


def _read_wav(path: Path) -> tuple[np.ndarray, int, int]:
    """Return float32 mono samples in [-1, 1], sample rate, channel count of source."""
    with wave.open(str(path), "rb") as wf:
        nch = wf.getnchannels()
        sw = wf.getsampwidth()
        sr = wf.getframerate()
        nframes = wf.getnframes()
        raw = wf.readframes(nframes)
    if sw != 2:
        raise MusicDirectorError(f"only 16-bit PCM wav supported without ffmpeg: {path}")
    data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if nch > 1:
        data = data.reshape(-1, nch).mean(axis=1)
    return data, int(sr), int(nch)


def _ffmpeg_decode_to_wav(source: Path, dest: Path, *, sr: int = 48000) -> Path:
    """Decode any ffmpeg-readable media to mono s16le wav."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    from util.subprocess import run_ffmpeg

    run_ffmpeg(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(source),
            "-vn",
            "-ac",
            "1",
            "-ar",
            str(int(sr)),
            "-c:a",
            "pcm_s16le",
            str(dest),
        ],
        check=True,
    )
    if not dest.is_file():
        raise MusicDirectorError(f"ffmpeg failed to decode audio from {source}")
    return dest


def load_audio_samples(
    path: Path,
    *,
    work_dir: Path | None = None,
    target_sr: int = 48000,
) -> tuple[np.ndarray, int, dict[str, Any]]:
    """Load mono float samples from wav or any ffmpeg media.

    Returns (samples, sr, meta) where meta notes decode path.
    """
    path = Path(path)
    meta: dict[str, Any] = {"source": str(path), "decode": "wav"}
    if path.suffix.lower() == ".wav":
        try:
            samples, sr, nch = _read_wav(path)
            meta["channels_src"] = nch
            return samples, sr, meta
        except (MusicDirectorError, wave.Error, EOFError) as exc:
            meta["wav_direct_error"] = str(exc)[:160]
    # ffmpeg path for mp3/m4a/mp4/video or broken wav
    tmp_root = Path(work_dir) if work_dir is not None else path.parent
    tmp_root.mkdir(parents=True, exist_ok=True)
    tmp = tmp_root / f"_md_decode_{path.stem}_{abs(hash(str(path))) % 10_000_000}.wav"
    try:
        _ffmpeg_decode_to_wav(path, tmp, sr=target_sr)
        samples, sr, nch = _read_wav(tmp)
        meta.update({"decode": "ffmpeg", "channels_src": nch, "decoded_wav": str(tmp)})
        return samples, sr, meta
    except Exception as exc:  # noqa: BLE001
        raise MusicDirectorError(f"cannot load audio from {path}: {exc}") from exc
    finally:
        # keep decoded temp only if work_dir provided for audit; else delete
        if work_dir is None and tmp.is_file():
            try:
                tmp.unlink()
            except OSError:
                pass


def apply_light_process_samples(samples: np.ndarray, sr: int) -> np.ndarray:
    """Mild H3-native-aligned cleanup without agate / dual arnndn.

    - DC remove
    - simple 1-pole highpass ~80Hz
    - soft clip guard (does not replace peak_fix)
    """
    if samples.size == 0:
        return samples
    out = samples.astype(np.float32).copy()
    out = out - float(np.mean(out))
    # one-pole highpass ~80 Hz
    fc = 80.0
    x = float(np.exp(-2.0 * np.pi * fc / max(float(sr), 1.0)))
    y = 0.0
    prev = 0.0
    hp = np.empty_like(out)
    for i, s in enumerate(out):
        y = x * (y + s - prev)
        prev = s
        hp[i] = y
    # soft ceiling only (peak_fix still owns true-peak policy)
    return np.clip(hp, -0.98, 0.98)


def _write_wav_mono(path: Path, samples: np.ndarray, sr: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    clipped = np.clip(samples, -1.0, 1.0)
    pcm = (clipped * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(int(sr))
        wf.writeframes(pcm.tobytes())


def _max_dbfs(samples: np.ndarray) -> float:
    peak = float(np.max(np.abs(samples))) if samples.size else 0.0
    if peak <= 1e-12:
        return -120.0
    return 20.0 * float(np.log10(peak))


def apply_mute_windows_samples(
    samples: np.ndarray,
    sr: int,
    windows: list[dict[str, Any]],
    *,
    mute_entire: bool = False,
) -> np.ndarray:
    """Zero samples in plate-local mute windows (or entire clip)."""
    out = samples.copy()
    if mute_entire:
        out[:] = 0.0
        return out
    n = len(out)
    for win in windows:
        start = max(0, int(float(win["start_sec"]) * sr))
        end = min(n, int(float(win["end_sec"]) * sr))
        if end > start:
            out[start:end] = 0.0
    return out


def apply_peak_fix_samples(
    samples: np.ndarray,
    *,
    true_peak_dbtp: float = -1.5,
    gain: float = 1.0,
    peak_fix: str = "auto",
    limiter: float = 0.95,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Scale by gain; if auto and over true-peak target, reduce + soft clip to limiter."""
    before = _max_dbfs(samples)
    out = samples.astype(np.float32) * float(gain)
    applied_gain = float(gain)
    if peak_fix == "auto" and out.size:
        target_lin = 10 ** (float(true_peak_dbtp) / 20.0)
        peak = float(np.max(np.abs(out)))
        if peak > target_lin and peak > 1e-12:
            scale = target_lin / peak
            out = out * scale
            applied_gain *= scale
    # Soft ceiling (matches final mix alimiter spirit)
    lim = max(0.5, min(1.0, float(limiter)))
    out = np.clip(out, -lim, lim)
    after = _max_dbfs(out)
    return out, {
        "peak_dbfs_before": round(before, 3),
        "peak_dbfs_after": round(after, 3),
        "applied_gain": round(applied_gain, 6),
        "peak_fix": peak_fix,
        "true_peak_dbtp": true_peak_dbtp,
        "limiter": lim,
    }


def apply_native_voice_plan(
    root: Path,
    plan: dict[str, Any] | None = None,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Apply mute windows + peak fix; write audio/native_directed/{shot_id}.wav."""
    root = Path(root).expanduser().resolve()
    plan = normalize_plan(plan if plan is not None else (load_plan(root) or draft_plan(root=root)))
    peak_pol = plan["native_voice"]["peak_policy"]
    shot_rows: list[dict[str, Any]] = []
    ok = True
    for row in plan["native_voice"]["shots"]:
        sid = row["shot_id"]
        entry: dict[str, Any] = {
            "shot_id": sid,
            "lane": row["lane"],
            "mute_entire": row["mute_entire"],
            "mute_windows": row["mute_windows"],
            "status": "pending",
        }
        if row["lane"] == "post_tts":
            entry["status"] = "skipped_post_tts"
            entry["note"] = "music director apply only processes native/silence stems"
            shot_rows.append(entry)
            continue
        source = discover_native_source(root, sid)
        if source is None:
            if row["mute_entire"] or row["lane"] == "silence":
                entry["status"] = "no_source_silence_ok"
                entry["note"] = "no native file; silence lane needs no stem"
                shot_rows.append(entry)
                continue
            entry["status"] = "missing_source"
            entry["ok"] = False
            ok = False
            shot_rows.append(entry)
            continue
        try:
            work = root / "audio" / "_music_director_work"
            samples, sr, decode_meta = load_audio_samples(source, work_dir=work)
        except MusicDirectorError as exc:
            entry["status"] = "read_error"
            entry["error"] = str(exc)
            entry["ok"] = False
            ok = False
            shot_rows.append(entry)
            continue
        source_sha = sha256_file(source)
        process = str(plan["native_voice"].get("default_process") or "light")
        if process == "light":
            samples = apply_light_process_samples(samples, sr)
        muted = apply_mute_windows_samples(
            samples,
            sr,
            row["mute_windows"],
            mute_entire=bool(row["mute_entire"] or row["lane"] == "silence"),
        )
        fixed, peak_meta = apply_peak_fix_samples(
            muted,
            true_peak_dbtp=float(peak_pol["true_peak_dbtp"]),
            gain=float(row["gain"]),
            peak_fix=str(row["peak_fix"]),
            limiter=float(peak_pol["limiter"]),
        )
        peak_meta = {**peak_meta, "decode": decode_meta.get("decode"), "process": process}
        dest = directed_stem_path(root, sid)
        if not dry_run:
            _write_wav_mono(dest, fixed, sr)
            dest_sha = sha256_file(dest)
        else:
            dest_sha = None
        entry.update(
            {
                "status": "applied" if not dry_run else "dry_run",
                "ok": True,
                "source": str(source),
                "source_sha256": source_sha,
                "directed": str(dest) if not dry_run else None,
                "directed_sha256": dest_sha,
                "sample_rate": sr,
                "duration_sec": round(len(fixed) / float(sr), 4) if sr else 0.0,
                "peak": peak_meta,
            }
        )
        shot_rows.append(entry)

    receipt = {
        "schema": "aifilm-music-director-apply-v1",
        "ok": ok,
        "partial": (not ok) and any(r.get("status") == "applied" for r in shot_rows),
        "created_at": utc_now(),
        "plan_schema": SCHEMA,
        "audio_policy": plan.get("audio_policy"),
        "directed_dir": str(directed_dir(root)),
        "dry_run": dry_run,
        "shots": shot_rows,
        "mute_window_count": sum(len(r.get("mute_windows") or []) for r in plan["native_voice"]["shots"]),
        "peak_fixed_count": sum(
            1
            for r in shot_rows
            if isinstance(r.get("peak"), dict)
            and float(r["peak"].get("peak_dbfs_before", -99))
            > float(plan["native_voice"]["peak_policy"]["true_peak_dbtp"])
        ),
    }
    if not dry_run:
        out = apply_receipt_path(root)
        out.parent.mkdir(parents=True, exist_ok=True)
        write_json(out, receipt)
        receipt["path"] = str(out)
    return receipt


def apply_bgm_plan(
    root: Path,
    plan: dict[str, Any] | None = None,
    *,
    patch_spec: bool = False,
) -> dict[str, Any]:
    """Record BGM plan application; optionally patch film-spec music_cue fields."""
    root = Path(root).expanduser().resolve()
    plan = normalize_plan(plan if plan is not None else (load_plan(root) or draft_plan(root=root)))
    patched = 0
    if patch_spec:
        spec_path = root / "film-spec.json"
        if not spec_path.is_file():
            raise MusicDirectorError("patch_spec requires film-spec.json")
        spec = _load_spec(root)
        shots = _flatten_shots(spec)
        patched = apply_bgm_to_shots(shots, plan)
        # also silence lanes onto dialogue_audio_lane
        voice_by = {r["shot_id"]: r for r in plan["native_voice"]["shots"]}
        for shot in shots:
            sid = str(shot.get("id") or "")
            vr = voice_by.get(sid)
            if vr and vr.get("lane") in _LANES:
                shot["dialogue_audio_lane"] = vr["lane"]
        write_json(spec_path, spec)
    return {
        "ok": True,
        "bgm_shot_count": len(plan["bgm"]["shots"]),
        "default_mood": plan["bgm"]["default_mood"],
        "global_gain": plan["bgm"]["global_gain"],
        "spec_patched": patch_spec,
        "music_cue_patched": patched,
    }


def apply_plan(
    root: Path,
    plan: dict[str, Any] | None = None,
    *,
    dry_run: bool = False,
    patch_spec: bool = False,
) -> dict[str, Any]:
    """Full apply: save plan, native stems, BGM overlay report."""
    root = Path(root).expanduser().resolve()
    if plan is None:
        plan = load_plan(root) or draft_plan(root=root)
    plan = normalize_plan(plan)
    if not dry_run:
        save_plan(root, plan)
    native = apply_native_voice_plan(root, plan, dry_run=dry_run)
    bgm = apply_bgm_plan(root, plan, patch_spec=patch_spec and not dry_run)
    return {
        "ok": bool(native.get("ok")) and bool(bgm.get("ok")),
        "plan_path": str(plan_path(root)),
        "native": native,
        "bgm": bgm,
    }


def resolve_directed_native_path(
    root: Path,
    shot_id: str,
    *,
    source_path: Path | None = None,
    receipt: dict[str, Any] | None = None,
) -> Path | None:
    """Return directed stem if apply receipt proves it for this shot.

    Prefer directed only when receipt lists applied + matching source sha (if known).
    """
    root = Path(root).expanduser().resolve()
    dest = directed_stem_path(root, shot_id)
    if not dest.is_file():
        return None
    if receipt is None:
        rpath = apply_receipt_path(root)
        if rpath.is_file():
            raw = read_json(rpath)
            receipt = raw if isinstance(raw, dict) else None
    if not isinstance(receipt, dict):
        # No receipt: still allow directed file (explicit desk product)
        return dest
    for row in receipt.get("shots") or []:
        if not isinstance(row, dict):
            continue
        if str(row.get("shot_id")) != shot_id:
            continue
        if row.get("status") not in {"applied", "dry_run"}:
            return None
        if source_path is not None and row.get("source_sha256"):
            try:
                if sha256_file(source_path) != row.get("source_sha256"):
                    return None
            except OSError:
                return None
        if row.get("directed_sha256") and dest.is_file():
            try:
                if sha256_file(dest) != row.get("directed_sha256"):
                    return None
            except OSError:
                return None
        return dest
    return None


def build_review(root: Path, plan: dict[str, Any] | None = None) -> dict[str, Any]:
    """Human listen map: mutes, peaks, BGM ducks, listen points."""
    root = Path(root).expanduser().resolve()
    plan = normalize_plan(plan if plan is not None else (load_plan(root) or draft_plan(root=root)))
    receipt = None
    rpath = apply_receipt_path(root)
    if rpath.is_file():
        raw = read_json(rpath)
        if isinstance(raw, dict):
            receipt = raw
    mute_list: list[dict[str, Any]] = []
    for row in plan["native_voice"]["shots"]:
        if row["mute_entire"] or row["lane"] == "silence":
            mute_list.append(
                {
                    "shot_id": row["shot_id"],
                    "kind": "entire",
                    "reason": row.get("reason") or "silence_lane",
                }
            )
        for win in row["mute_windows"]:
            mute_list.append(
                {
                    "shot_id": row["shot_id"],
                    "kind": "window",
                    "start_sec": win["start_sec"],
                    "end_sec": win["end_sec"],
                    "reason": win.get("reason"),
                }
            )
    ducks = [
        {"shot_id": r["shot_id"], "duck_db": r["duck_db"], "mute_bed": r["mute_bed"]}
        for r in plan["bgm"]["shots"]
        if r["duck_db"] < 0 or r["mute_bed"]
    ]
    peak_rows = []
    if isinstance(receipt, dict):
        for row in receipt.get("shots") or []:
            if isinstance(row, dict) and isinstance(row.get("peak"), dict):
                peak_rows.append(
                    {
                        "shot_id": row["shot_id"],
                        **row["peak"],
                        "status": row.get("status"),
                    }
                )
    status = "ready_for_human_listen"
    if mute_list or any(
        isinstance(p.get("peak_dbfs_before"), (int, float))
        and p["peak_dbfs_before"] > plan["native_voice"]["peak_policy"]["true_peak_dbtp"]
        for p in peak_rows
    ):
        status = "needs_attention" if mute_list else status
    return {
        "schema": "aifilm-music-director-review-v1",
        "status": status,
        "plan_path": str(plan_path(root)),
        "audio_policy": plan.get("audio_policy"),
        "bgm": {
            "default_mood": plan["bgm"]["default_mood"],
            "global_gain": plan["bgm"]["global_gain"],
            "duck_rows": ducks,
        },
        "native_voice": {
            "mute_actions": mute_list,
            "peak_rows": peak_rows,
            "default_process": plan["native_voice"]["default_process"],
            "peak_policy": plan["native_voice"]["peak_policy"],
        },
        "apply_receipt": str(rpath) if rpath.is_file() else None,
        "apply_ok": None if receipt is None else bool(receipt.get("ok")),
        "human_listen_points_sec": list(plan["review"].get("listen_points_sec") or []),
        "notes": plan["review"].get("notes") or "",
        "picture_timing_changed": False,
        "wrong_line_policy": "audio_mute_v1",
    }




def set_shot_controls(
    plan: dict[str, Any],
    shot_id: str,
    *,
    mute_window: tuple[float, float] | None = None,
    mute_reason: str = "wrong_line",
    mute_entire: bool | None = None,
    peak_fix: str | None = None,
    gain: float | None = None,
    lane: str | None = None,
    duck_db: float | None = None,
    energy: float | None = None,
    mute_bed: bool | None = None,
) -> dict[str, Any]:
    """Director convenience: mutate one shot in plan (native + optional BGM)."""
    plan = normalize_plan(plan)
    sid = str(shot_id).strip()
    if not sid:
        raise MusicDirectorError("shot_id required")
    voice_by = {r["shot_id"]: dict(r) for r in plan["native_voice"]["shots"]}
    row = voice_by.get(sid) or {
        "shot_id": sid,
        "lane": "native",
        "gain": 1.0,
        "peak_fix": "auto",
        "mute_windows": [],
        "mute_entire": False,
        "reason": "director_set",
        "caption_policy": "keep_chinese",
    }
    if mute_window is not None:
        start, end = float(mute_window[0]), float(mute_window[1])
        wins = list(row.get("mute_windows") or [])
        wins.append(
            {
                "start_sec": start,
                "end_sec": end,
                "reason": mute_reason,
                "source": "director",
            }
        )
        row["mute_windows"] = wins
    if mute_entire is not None:
        row["mute_entire"] = bool(mute_entire)
        if row["mute_entire"]:
            row["lane"] = "silence"
    if peak_fix is not None:
        row["peak_fix"] = peak_fix
    if gain is not None:
        row["gain"] = float(gain)
    if lane is not None:
        row["lane"] = lane
    if mute_reason and mute_window is not None:
        row["reason"] = mute_reason
    voice_by[sid] = row
    plan["native_voice"]["shots"] = list(voice_by.values())

    if any(v is not None for v in (duck_db, energy, mute_bed)):
        bgm_by = {r["shot_id"]: dict(r) for r in plan["bgm"]["shots"]}
        brow = bgm_by.get(sid) or {
            "shot_id": sid,
            "mood": plan["bgm"]["default_mood"],
            "energy": 0.55,
            "duck_db": 0.0,
            "mute_bed": False,
        }
        if duck_db is not None:
            brow["duck_db"] = float(duck_db)
        if energy is not None:
            brow["energy"] = float(energy)
        if mute_bed is not None:
            brow["mute_bed"] = bool(mute_bed)
        bgm_by[sid] = brow
        plan["bgm"]["shots"] = list(bgm_by.values())
    plan["source"] = "director"
    return normalize_plan(plan)


def audit_native_peaks(root: Path, plan: dict[str, Any] | None = None) -> dict[str, Any]:
    """Probe max peak per discovered source; suggest listen points for hot stems."""
    root = Path(root).expanduser().resolve()
    plan = normalize_plan(plan if plan is not None else (load_plan(root) or draft_plan(root=root)))
    thr = float(plan["native_voice"]["peak_policy"]["true_peak_dbtp"])
    rows: list[dict[str, Any]] = []
    listen: list[float] = []
    work = root / "audio" / "_music_director_work"
    for row in plan["native_voice"]["shots"]:
        sid = row["shot_id"]
        src = discover_native_source(root, sid)
        if src is None:
            rows.append({"shot_id": sid, "status": "missing_source"})
            continue
        try:
            samples, sr, meta = load_audio_samples(src, work_dir=work)
            peak = _max_dbfs(samples)
            hot = peak > thr
            item = {
                "shot_id": sid,
                "status": "ok",
                "source": str(src),
                "peak_dbfs": round(peak, 3),
                "hot": hot,
                "threshold_dbtp": thr,
                "decode": meta.get("decode"),
                "duration_sec": round(len(samples) / float(sr), 3) if sr else 0.0,
            }
            rows.append(item)
            if hot:
                listen.append(0.0)  # plate-local; review maps by shot
        except MusicDirectorError as exc:
            rows.append({"shot_id": sid, "status": "error", "error": str(exc)[:200]})
    hot_ids = [r["shot_id"] for r in rows if r.get("hot")]
    return {
        "schema": "aifilm-music-director-audit-v1",
        "ok": all(r.get("status") in {"ok", "missing_source"} for r in rows),
        "true_peak_dbtp": thr,
        "hot_shot_ids": hot_ids,
        "shots": rows,
        "suggest_peak_fix_auto": hot_ids,
    }


def apply_batch_edits(plan: dict[str, Any], edits: list[dict[str, Any]]) -> dict[str, Any]:
    """Apply a list of director edit rows onto a plan."""
    if not isinstance(edits, list):
        raise MusicDirectorError("batch edits must be a list")
    plan = normalize_plan(plan)
    for raw in edits:
        if not isinstance(raw, dict):
            raise MusicDirectorError("each batch edit must be an object")
        sid = str(raw.get("shot_id") or raw.get("shot") or "").strip()
        if not sid:
            raise MusicDirectorError("batch edit missing shot_id")
        mute_window = None
        if raw.get("mute_window") is not None:
            mw = raw["mute_window"]
            if isinstance(mw, (list, tuple)) and len(mw) == 2:
                mute_window = (float(mw[0]), float(mw[1]))
            elif isinstance(mw, str):
                token = mw if ":" in mw else mw.replace("-", ":", 1)
                a, b = token.split(":", 1)
                mute_window = (float(a), float(b))
            else:
                raise MusicDirectorError(
                    f"shot {sid}: mute_window must be [start,end] or START:END"
                )
        plan = set_shot_controls(
            plan,
            sid,
            mute_window=mute_window,
            mute_reason=str(raw.get("reason") or raw.get("mute_reason") or "wrong_line"),
            mute_entire=raw.get("mute_entire"),
            peak_fix=raw.get("peak_fix"),
            gain=raw.get("gain"),
            lane=raw.get("lane"),
            duck_db=raw.get("duck_db"),
            energy=raw.get("energy"),
            mute_bed=raw.get("mute_bed"),
        )
        extra = raw.get("mute_windows")
        if isinstance(extra, list):
            for win in extra:
                if not isinstance(win, dict):
                    continue
                plan = set_shot_controls(
                    plan,
                    sid,
                    mute_window=(float(win["start_sec"]), float(win["end_sec"])),
                    mute_reason=str(win.get("reason") or raw.get("reason") or "wrong_line"),
                )
    return normalize_plan(plan)


def load_batch_edits(path: Path) -> list[dict[str, Any]]:
    """Load edits from .json (list/object) or .jsonl (one object per line)."""
    import json as _json

    path = Path(path)
    if not path.is_file():
        raise MusicDirectorError(f"batch file missing: {path}")
    raw = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".jsonl":
        edits: list[dict[str, Any]] = []
        for i, line in enumerate(raw.splitlines(), start=1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                obj = _json.loads(line)
            except Exception as exc:  # noqa: BLE001
                raise MusicDirectorError(f"jsonl line {i} invalid: {exc}") from exc
            if not isinstance(obj, dict):
                raise MusicDirectorError(f"jsonl line {i} must be an object")
            edits.append(obj)
        return edits
    data = _json.loads(raw)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        if isinstance(data.get("edits"), list):
            return data["edits"]
        if data.get("shot_id") or data.get("shot"):
            return [data]
    raise MusicDirectorError("batch JSON must be a list, {edits:[...]}, or one edit object")


def export_listen_checklist(
    root: Path,
    plan: dict[str, Any] | None = None,
    *,
    audit: dict[str, Any] | None = None,
    write: bool = True,
) -> dict[str, Any]:
    """Build a human listen checklist from plan + optional peak audit + apply receipt."""
    root = Path(root).expanduser().resolve()
    plan = normalize_plan(plan if plan is not None else (load_plan(root) or draft_plan(root=root)))
    review = build_review(root, plan)
    if audit is None:
        try:
            audit = audit_native_peaks(root, plan)
        except MusicDirectorError:
            audit = {"ok": False, "hot_shot_ids": [], "shots": []}

    hot = {str(x) for x in (audit.get("hot_shot_ids") or [])}
    audit_by = {
        str(r.get("shot_id")): r
        for r in (audit.get("shots") or [])
        if isinstance(r, dict) and r.get("shot_id")
    }
    items: list[dict[str, Any]] = []
    for vrow in plan["native_voice"]["shots"]:
        sid = vrow["shot_id"]
        bgm = next((b for b in plan["bgm"]["shots"] if b["shot_id"] == sid), None) or {}
        arow = audit_by.get(sid) or {}
        mutes = list(vrow.get("mute_windows") or [])
        flags: list[str] = []
        if vrow.get("mute_entire") or vrow.get("lane") == "silence":
            flags.append("mute_entire")
        if mutes:
            flags.append(f"mute_windows={len(mutes)}")
        if sid in hot:
            flags.append("peak_hot")
        if float(bgm.get("duck_db") or 0) < 0:
            flags.append(f"duck={bgm.get('duck_db')}")
        if bgm.get("mute_bed"):
            flags.append("mute_bed")
        priority = 0
        if "peak_hot" in flags:
            priority += 2
        if mutes or "mute_entire" in flags:
            priority += 2
        if any(f.startswith("duck") for f in flags):
            priority += 1
        items.append(
            {
                "shot_id": sid,
                "lane": vrow.get("lane"),
                "priority": priority,
                "flags": flags,
                "mute_windows": mutes,
                "mute_entire": bool(vrow.get("mute_entire")),
                "peak_dbfs": arow.get("peak_dbfs"),
                "hot": bool(arow.get("hot")),
                "source": arow.get("source"),
                "duration_sec": arow.get("duration_sec"),
                "duck_db": bgm.get("duck_db"),
                "listen_note": (
                    "抽听 peak + mute 窗后"
                    if priority >= 2
                    else ("抽听 1 句" if vrow.get("lane") == "native" else "可跳过 silence")
                ),
                "done": False,
            }
        )
    items.sort(key=lambda r: (-int(r["priority"]), str(r["shot_id"])))
    must = [r for r in items if int(r["priority"]) >= 2]
    lines = [
        "# Music Director 抽听清单",
        "",
        f"- root: `{root}`",
        f"- must_listen: **{len(must)}** / {len(items)}",
        f"- hot_peaks: {len(hot)}",
        f"- policy: audio mute v1（不改画面）",
        "",
        "| pri | shot | flags | peak | note | done |",
        "|----:|------|-------|-----:|------|------|",
    ]
    for r in items:
        flags = ",".join(r["flags"]) or "—"
        peak = r["peak_dbfs"] if r["peak_dbfs"] is not None else "—"
        lines.append(
            f"| {r['priority']} | `{r['shot_id']}` | {flags} | {peak} | {r['listen_note']} | [ ] |"
        )
    lines.extend(
        [
            "",
            "## 操作提示",
            "1. 先听 priority≥2（mute / 爆音）",
            "2. 改窗：`aifilm music-director set --shot … --mute-window a:b`",
            "3. 批改：`aifilm music-director batch --file edits.json`",
            "4. `apply` → `final`",
            "",
        ]
    )
    md_body = "\n".join(lines)
    checklist = {
        "schema": "aifilm-music-director-checklist-v1",
        "created_at": utc_now(),
        "root": str(root),
        "plan_path": str(plan_path(root)),
        "audio_policy": plan.get("audio_policy"),
        "counts": {
            "shots": len(items),
            "must_listen": len(must),
            "hot_peaks": len(hot),
            "mute_actions": sum(1 for r in items if r["mute_windows"] or r["mute_entire"]),
        },
        "items": items,
        "review_status": review.get("status"),
        "audit_ok": audit.get("ok"),
        "picture_timing_changed": False,
        "wrong_line_policy": "audio_mute_v1",
        "markdown": md_body,
    }
    if write:
        out_json = root / "receipts" / "music-director-checklist.json"
        out_md = root / "receipts" / "music-director-checklist.md"
        out_json.parent.mkdir(parents=True, exist_ok=True)
        payload = {k: v for k, v in checklist.items() if k != "markdown"}
        write_json(out_json, payload)
        out_md.write_text(md_body, encoding="utf-8")
        checklist["path_json"] = str(out_json)
        checklist["path_md"] = str(out_md)
    return checklist


def apply_audit_peak_suggestions(
    plan: dict[str, Any],
    audit: dict[str, Any],
    *,
    force_auto: bool = True,
) -> dict[str, Any]:
    """For hot peak shots, set peak_fix=auto (idempotent)."""
    plan = normalize_plan(plan)
    for sid in [str(x) for x in (audit.get("hot_shot_ids") or [])]:
        plan = set_shot_controls(plan, sid, peak_fix="auto" if force_auto else None)
    return normalize_plan(plan)


def draft_and_save(root: Path) -> dict[str, Any]:
    plan = draft_plan(root=root)
    path = save_plan(root, plan)
    return {"ok": True, "path": str(path), "plan": plan}

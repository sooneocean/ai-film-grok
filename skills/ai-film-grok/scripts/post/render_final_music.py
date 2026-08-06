#!/usr/bin/env python3
"""BGM / WAV / loudness helpers for final render.

Extracted from render_final.py (C4 · 2026-08-04). Re-exported by render_final
for backward compatibility (tests import SR, procedural_music, etc. from render_final).
"""

from __future__ import annotations

import os
import re
import subprocess
import wave
from pathlib import Path
from typing import Any

import numpy as np
from logger import log
from runtime_policy import sha256
from sound_plan import resolve_music_template_timeline
from util import run_ffmpeg, write_json
from util.errors import FilmError

# Local defs — avoid circular import with render_final (which re-exports this module).
SR = 44100


class RenderError(FilmError):
    pass


def run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Subprocess runner: ffmpeg gets -nostdin + AIFILM_FFMPEG_TIMEOUT; others use the canonical 60s timeout."""
    argv = list(cmd)
    executable = Path(argv[0]).name if argv else ""
    if executable == "ffmpeg":
        return run_ffmpeg(argv, check=check)
    from util.subprocess import run as util_run

    return util_run(cmd, check=check, timeout=60)


try:
    from music_cue import motif_seed
except ImportError:  # pragma: no cover
    motif_seed = None  # type: ignore


def make_tone(
    f0: float,
    a: float,
    n_seg: int,
    sr: int = SR,
    vib: float = 4.5,
    atk: float = 0.05,
    rel: float = 0.4,
) -> np.ndarray:
    tt = np.linspace(0, n_seg / sr, n_seg, endpoint=False)
    env = np.ones(n_seg)
    atk_n = max(1, int(sr * atk))
    rel_n = max(1, int(sr * rel))
    env[:atk_n] = np.linspace(0, 1, atk_n)
    env[-rel_n:] = np.linspace(1, 0, rel_n)
    vib_ = 1 + 0.006 * np.sin(2 * np.pi * vib * tt)
    return a * env * np.sin(2 * np.pi * f0 * vib_ * tt)


def _try_external_music_gen(
    *,
    work: Path,
    duration: float,
    mood: str,
    seed: int,
    title: str,
) -> dict[str, Any] | None:
    """Optional AI music via AIFILM_MUSIC_ARGV (same security model as TTS external).

    Env:
      AIFILM_MUSIC_ARGV='["python3","…/music_external.py","--out","{out}","--duration","{duration}",
        "--mood","{mood}","--seed","{seed}","--prompt","{prompt}"]'
    Only runs when set; failure is non-fatal (falls through to procedural) unless
    AIFILM_MUSIC_REQUIRE=1.
    """
    raw = (os.environ.get("AIFILM_MUSIC_ARGV") or "").strip()
    if not raw:
        return None
    out = work / "bgm_external.wav"
    prompt = (
        os.environ.get("AIFILM_MUSIC_PROMPT")
        or f"instrumental background music, {mood}, cinematic soft, no vocals, for short film '{title}'"
    )
    try:
        from security_policy import (  # type: ignore
            expand_argv,
            minimal_subprocess_env,
            parse_argv_json,
        )

        template = parse_argv_json(raw, variable="AIFILM_MUSIC_ARGV")
        argv = expand_argv(
            template,
            {
                "out": str(out),
                "duration": f"{duration:.3f}",
                "mood": str(mood),
                "seed": str(int(seed)),
                "prompt": prompt,
                "title": title,
            },
            variable="AIFILM_MUSIC_ARGV",
        )
        env = minimal_subprocess_env()
        # Allow adapter to re-read config; do not pass API keys blindly
        log(f"BGM external gen: {' '.join(argv[:4])}…")
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            env=env,
            timeout=float(os.environ.get("AIFILM_MUSIC_TIMEOUT") or 600),
        )
        if proc.returncode != 0 or not out.is_file() or out.stat().st_size < 500:
            msg = (proc.stderr or proc.stdout or "")[-400:]
            if os.environ.get("AIFILM_MUSIC_REQUIRE") == "1":
                raise RenderError(f"AIFILM_MUSIC_ARGV failed (require=1): {msg}")
            log(f"BGM external gen failed → procedural: {msg}")
            return None
        return {
            "path": str(out.resolve()),
            "license_note": os.environ.get("AIFILM_MUSIC_LICENSE")
            or "external generative music (AIFILM_MUSIC_ARGV) — verify model license",
            "source": "external_music",
            "mood": mood,
            "mode": "auto",
            "relative": str(out),
        }
    except RenderError:
        raise
    except Exception as exc:
        if os.environ.get("AIFILM_MUSIC_REQUIRE") == "1":
            raise RenderError(f"AIFILM_MUSIC_ARGV error: {exc}") from exc
        log(f"BGM external gen error → procedural: {exc}")
        return None


def procedural_music_rnb(
    dur: float,
    *,
    amp: float = 0.16,
    bpm: float = 76.0,
    seed: int | None = None,
    shot_starts: list[float] | None = None,
    events: list[dict] | None = None,
    density: float = 0.5,
    bass_presence: float = 0.5,
    brightness: float = 0.5,
    key_shift: int = 0,
) -> np.ndarray:
    """Seductive late-night R&B bed (Rhodes + sub + soft kit). float mono."""
    # Prefer shared implementation from make_sfx_bed when available
    try:
        from make_sfx_bed import rnb_bgm  # type: ignore

        return rnb_bgm(
            dur,
            amp=amp,
            bpm=bpm,
            seed=seed,
            shot_starts=shot_starts,
            events=events,
            density=density,
            bass_presence=bass_presence,
            brightness=brightness,
            key_shift=key_shift,
        )
    except Exception:
        pass
    n = int(SR * max(0.5, dur))
    t = np.linspace(0, dur, n, endpoint=False)
    # fallback: warm minor pad + pulse + soft kick grid
    sig = np.zeros(n)
    for f in (110.0, 164.8, 220.0, 261.6, 329.6):
        sig += 0.08 * np.sin(2 * np.pi * f * t)
    beat = 60.0 / bpm
    pump = 0.65 + 0.35 * (0.5 + 0.5 * np.sin(2 * np.pi * (2.0 / beat) * t))
    sig *= pump
    # soft kick thumps
    kick_len = int(0.08 * SR)
    i = 0
    while i < n:
        k = min(kick_len, n - i)
        env = np.linspace(1, 0, k) ** 2
        sig[i : i + k] += (
            0.22 * env * np.sin(2 * np.pi * 55 * np.linspace(0, 0.08, k, endpoint=False))
        )
        i += int(beat * 2 * SR)
    sig = np.tanh(sig * amp * 2.2)
    fade = int(SR * 1.0)
    if n > 2 * fade:
        sig[:fade] *= np.linspace(0, 1, fade)
        sig[-fade:] *= np.linspace(1, 0, fade)
    return sig


def procedural_music(
    dur: float,
    *,
    emo: float = 1.0,
    curve: str = "flat",
    amp: float = 0.14,
    mood: str = "playful",
    seed: int | None = None,
    shot_starts: list[float] | None = None,
    events: list[dict] | None = None,
    mood_timeline: list[dict] | None = None,
) -> np.ndarray:
    """Royalty-free algorithmic BGM (numpy). License: original generative, no sample pack.

    Returns int16 mono. Moods: playful | dark | warm | rnb.
    Phase 4: Plot-Adaptive Multi-Stem. Supports timeline of moods stitched with crossfades.
    """

    def _generate_single(
        g_dur: float,
        g_mood: str,
        g_seed: int | None,
        *,
        g_density: float = 0.5,
        g_bass_presence: float = 0.5,
        g_brightness: float = 0.5,
        g_bpm: float = 76.0,
        g_key_shift: int = 0,
        g_palette: tuple[str, ...] = (),
    ) -> np.ndarray:
        g_mood = (g_mood or "playful").lower()
        if g_mood in (
            "rnb",
            "r&b",
            "soul",
            "neo-soul",
            "neosoul",
            "sensual",
            "seductive",
            "ecchi",
            "sexy",
        ):
            sig = procedural_music_rnb(
                g_dur,
                amp=amp * 1.05,
                bpm=g_bpm,
                seed=g_seed,
                shot_starts=shot_starts,
                events=events,
                density=g_density,
                bass_presence=g_bass_presence,
                brightness=g_brightness,
                key_shift=g_key_shift,
            )
            n = len(sig)
            tt = np.linspace(0, g_dur, n, endpoint=False)
            if "upright_bass" in g_palette:
                sig += 0.035 * np.sin(2 * np.pi * 55.0 * tt)
            if "rhodes" in g_palette:
                sig += (
                    0.014
                    * np.sin(2 * np.pi * 440.0 * tt)
                    * (0.7 + 0.3 * np.sin(2 * np.pi * 5.0 * tt))
                )
            if "brush_drums" in g_palette:
                brush = np.sin(2 * np.pi * (g_bpm / 60.0) * tt) ** 12
                sig += 0.012 * brush * np.sin(2 * np.pi * 3200.0 * tt)
            return np.tanh(sig)

        n = int(SR * max(0.5, g_dur))
        seg_n = max(1, n // 4)
        n = seg_n * 4
        sig = np.zeros(n)
        tt = np.linspace(0, 1, n, endpoint=False)
        if curve == "rise":
            dyn = 0.45 + 0.55 * tt
        elif curve == "fall":
            dyn = 1.0 - 0.45 * tt
        elif curve == "swell":
            dyn = 0.4 + 0.6 * np.sin(np.pi * tt)
        else:
            dyn = np.ones(n)

        if g_mood == "playful":
            notes = [261.6, 329.6, 392.0, 523.3]
            bass = 130.8
            pad = [261.6, 329.6, 392.0]
            counter = [523.3, 493.9, 440.0, 392.0]
        elif g_mood == "dark":
            notes = [220.0, 261.6, 329.6, 440.0]
            bass = 110.0
            pad = [220.0, 261.6, 329.6]
            counter = [440.0, 392.0, 329.6, 293.7]
        elif g_mood == "ambient":
            # A suspended, low-motion pad palette: deliberately no bass ostinato
            # or melodic counterline, so establishing shots do not sound like a
            # warm-resolution cue with its volume turned down.
            notes = [196.0, 246.9, 293.7, 370.0]
            bass = 0.0
            pad = [196.0, 293.7, 370.0]
            counter = []
        else:  # warm
            notes = [246.9, 293.7, 370.0, 493.9]
            bass = 123.5
            pad = [246.9, 293.7, 370.0]
            counter = [493.9, 440.0, 370.0, 329.6]

        pitch = 2.0 ** (g_key_shift / 12.0)
        notes = [freq * pitch for freq in notes]
        pad = [freq * pitch for freq in pad]
        counter = [freq * pitch for freq in counter]
        bass *= pitch

        for i, f in enumerate(notes):
            s0, s1 = i * seg_n, (i + 1) * seg_n
            tone = make_tone(f, 0.15, seg_n)
            sig[s0:s1] += tone[: s1 - s0]
        for f in pad:
            sig += make_tone(f, 0.04, n, rel=n / SR)
        if bass:
            sig += make_tone(bass, 0.09, n, rel=n / SR)
        for i, f in enumerate(counter):
            s0, s1 = i * seg_n, (i + 1) * seg_n
            tone = make_tone(f, 0.035, seg_n, rel=0.2)
            sig[s0:s1] += tone[: s1 - s0]
        # Palette controls are deliberately small, instrumental colour shifts.
        # They give the recurring motif a new orchestration without replacing it
        # with an unrelated cue at every shot boundary.
        if "low_strings" in g_palette or "upright_bass" in g_palette:
            sig += 0.055 * np.sin(2 * np.pi * max(45.0, bass * 0.5) * tt * n / SR)
        if "warm_strings" in g_palette or "high_strings" in g_palette:
            sig += 0.022 * np.sin(2 * np.pi * notes[-1] * 2.0 * tt * n / SR)
        if "vibraphone" in g_palette or "marimba" in g_palette:
            shimmer = 0.5 + 0.5 * np.sin(2 * np.pi * (g_bpm / 60.0) * tt * n / SR)
            sig += 0.018 * shimmer * np.sin(2 * np.pi * notes[0] * 4.0 * tt * n / SR)
        t = tt * n / SR
        if "felt_piano" in g_palette or "prepared_piano" in g_palette:
            detune = 1.006 if "prepared_piano" in g_palette else 1.002
            sig += 0.014 * np.sin(2 * np.pi * notes[0] * detune * t)
        if "pizzicato_strings" in g_palette:
            sig += (
                0.016
                * np.sin(2 * np.pi * notes[-1] * 1.5 * t)
                * np.maximum(0, np.sin(2 * np.pi * g_bpm / 60.0 * t))
            )
        if "frame_drum" in g_palette:
            sig += (
                0.025
                * np.sin(2 * np.pi * 90.0 * t)
                * np.maximum(0, np.sin(2 * np.pi * g_bpm / 60.0 * t))
            )
        if "brush_drums" in g_palette:
            sig += (
                0.01
                * np.sin(2 * np.pi * 2600.0 * t)
                * np.maximum(0, np.sin(2 * np.pi * g_bpm / 60.0 * t))
            )
        # BPM creates a perceptible motion difference in the non-R&B palettes;
        # ambient moves slowly while suspense can pulse without changing genre.
        pulse_rate = max(0.15, g_bpm / 240.0)
        if g_mood == "ambient":
            sig *= 0.72 + 0.28 * np.sin(2 * np.pi * pulse_rate * tt) ** 2
        else:
            sig *= 0.84 + 0.16 * np.sin(2 * np.pi * pulse_rate * tt) ** 2
        sig *= amp * (1 + emo * 0.45) * dyn
        return np.tanh(sig)

    if not mood_timeline:
        final_float = _generate_single(dur, mood, seed)
        return (np.clip(final_float, -1, 1) * 32767).astype(np.int16)

    # Plot-Adaptive Dynamic Timeline with Equal-Power Crossfading & Anti-Fatigue Mutation
    final_bed = np.zeros(int(SR * dur))
    base_seed = seed or 42
    crossfade_sec = 2.5

    for i, chapter in enumerate(mood_timeline):
        st = float(chapter.get("start_sec", 0.0))
        ed = float(chapter.get("end_sec", dur))
        if ed > dur:
            ed = dur
        ch_dur = ed - st
        if ch_dur <= 0:
            continue

        next_transition = (
            str(mood_timeline[i + 1].get("transition") or "crossfade").lower()
            if i < len(mood_timeline) - 1
            else "cut"
        )
        overlap_sec = (
            crossfade_sec
            if next_transition == "crossfade"
            else 0.12
            if next_transition == "stinger"
            else 0.0
        )
        gen_dur = ch_dur + overlap_sec

        # Seed mutation: mutate seed per chapter index i
        chapter_seed = (
            motif_seed(base_seed, str(chapter.get("motif_id") or chapter.get("mood") or mood), i)
            if motif_seed is not None
            else base_seed + i
        )
        # `take_seed` is an authored variation knob. Keep the semantic motif
        # stable while changing its concrete take, rather than silently ignoring
        # the cue field or forcing a different genre.
        chapter_seed = (chapter_seed + int(chapter.get("seed", 0))) & 0x7FFFFFFF
        palette_value = chapter.get("instrument_palette")
        palette = (
            tuple(str(item) for item in palette_value if str(item))
            if isinstance(palette_value, (list, tuple))
            else ()
        )
        chapter_sig = _generate_single(
            gen_dur,
            str(chapter.get("mood", mood)),
            chapter_seed,
            g_density=float(chapter.get("density", 0.5)),
            g_bass_presence=float(chapter.get("bass_presence", 0.5)),
            g_brightness=float(chapter.get("brightness", 0.5)),
            g_bpm=float(chapter.get("bpm", 76.0)),
            g_key_shift=int(chapter.get("key_shift", 0)),
            g_palette=palette,
        )
        energy = max(0.0, min(1.0, float(chapter.get("energy", 0.55))))
        profile = str(chapter.get("stem_profile") or "full")
        chapter_sig *= 0.72 + 0.48 * energy
        if profile == "thin":
            chapter_sig *= 0.72
        elif profile == "silence":
            chapter_sig *= 0.0

        i0 = int(st * SR)
        i1 = i0 + len(chapter_sig)
        if i1 > len(final_bed):
            i1 = len(final_bed)
            chapter_sig = chapter_sig[: i1 - i0]

        span = len(chapter_sig)
        if span > 0:
            transition = str(chapter.get("transition") or "crossfade").lower()
            xfade_samples = min(int(crossfade_sec * SR), span)
            xfade_out_samples = min(int(crossfade_sec * SR), span)
            # An authored cut has no overlap; crossfade keeps constant acoustic
            # energy, while a stinger gets a short, intentional mute before the
            # incoming chapter. This makes the cue contract audible, not metadata.
            if transition == "cut":
                xfade_samples = 0
            elif transition == "stinger":
                xfade_samples = min(int(0.12 * SR), span)
                chapter_sig[:xfade_samples] *= np.linspace(0.0, 1.0, xfade_samples)
            if next_transition == "cut":
                xfade_out_samples = 0
            elif next_transition == "stinger":
                xfade_out_samples = min(int(0.12 * SR), span)
            if i > 0 and xfade_samples:
                t_in = np.linspace(0, 1, xfade_samples, endpoint=False)
                chapter_sig[:xfade_samples] *= np.sin(0.5 * np.pi * t_in)

            if i < len(mood_timeline) - 1 and xfade_out_samples:
                out_start = min(span, int(ch_dur * SR))
                out_span = min(xfade_out_samples, span - out_start)
                if out_span:
                    t_out = np.linspace(0, 1, out_span, endpoint=False)
                    chapter_sig[out_start : out_start + out_span] *= np.cos(0.5 * np.pi * t_out)

            final_bed[i0:i1] += chapter_sig

    return (np.clip(final_bed, -1, 1) * 32767).astype(np.int16)


def write_wav_mono(path: Path, samples: np.ndarray, sr: int = SR) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sr)
        handle.writeframes(samples.tobytes())


def write_wav_stereo(path: Path, samples: np.ndarray, sr: int = SR) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(sr)
        handle.writeframes(samples.tobytes())


def render_music_template_timeline(
    *,
    root: Path,
    work: Path,
    timeline: list[dict[str, Any]],
    plan: dict[str, Any] | None,
    music_license: str | None,
    seed: int,
    total_dur: float,
    approved_library: bool = False,
    film_id: str = "",
    series_id: str = "",
) -> tuple[np.ndarray, list[dict[str, Any]]]:
    """Render one licensed local template per cue into one mono BGM bed.

    A timeline choice is intentionally all-or-nothing: an absent mood-specific
    template blocks this mode rather than silently looping the film-wide bed.
    """
    if approved_library:
        from bgm_library import (
            BGMLibraryError,
            default_library_root,
            record_gaps,
            select_timeline,
        )

        library_root = default_library_root()
        try:
            selection_receipt = select_timeline(
                library_root,
                film_id=film_id or root.name,
                series_id=series_id,
                timeline=timeline,
                require_complete=False,
            )
        except BGMLibraryError as exc:
            raise RenderError(str(exc)) from exc
        write_json(root / "receipts" / "bgm-selection.json", selection_receipt)
        if selection_receipt["gaps"]:
            record_gaps(library_root, selection_receipt)
            missing = [f"{gap['shot_id']}:{gap['mood']}" for gap in selection_receipt["gaps"]]
            raise RenderError("approved_library missing approved BGM for: " + ", ".join(missing))
        from music_editor import build_music_edit_plan

        edit_plan = build_music_edit_plan(selection_receipt)
        write_json(root / "receipts" / "music-edit-plan.json", edit_plan)
        if not edit_plan["ready_for_final"]:
            required = sorted({str(item["kind"]) for item in edit_plan["requirements"]})
            raise RenderError(
                "approved_library music edit plan requires offline approved assets: "
                + ", ".join(required)
            )
        selections = selection_receipt["selections"]
    else:
        selections = resolve_music_template_timeline(
            root,
            timeline=timeline,
            plan=plan,
            music_license=music_license,
            seed=seed,
        )
    expected_ids = [str(item.get("shot_id") or "") for item in timeline]
    selected_ids = [str(item.get("shot_id") or "") for item in selections]
    if selected_ids != expected_ids:
        missing = sorted(set(expected_ids) - set(selected_ids))
        raise RenderError(
            "music_template=timeline missing mood-specific local BGM for: " + ", ".join(missing)
        )

    work.mkdir(parents=True, exist_ok=True)
    total = int(SR * total_dur)
    bed = np.zeros(total, dtype=np.float64)
    for index, selection in enumerate(selections):
        start = max(0.0, float(selection.get("start_sec") or 0.0))
        end = min(total_dur, float(selection.get("end_sec") or total_dur))
        if end <= start:
            continue
        if approved_library:
            selected_duration = float(selection.get("duration_sec") or 0.0)
            cue_duration = end - start
            if abs(selected_duration - cue_duration) > 0.001:
                raise RenderError("approved_library asset duration does not exactly match its cue")
        next_transition = (
            str(timeline[index + 1].get("transition") or "crossfade").lower()
            if index < len(timeline) - 1
            else "cut"
        )
        overlap = (
            2.5 if next_transition == "crossfade" else 0.12 if next_transition == "stinger" else 0.0
        )
        segment_dur = min(total_dur - start, end - start + overlap)
        wav_path = work / f"bgm_timeline_{index:03d}.wav"
        run(
            [
                "ffmpeg",
                "-y",
                "-stream_loop",
                "-1",
                "-i",
                str(selection["path"]),
                "-t",
                f"{segment_dur:.3f}",
                "-ar",
                str(SR),
                "-ac",
                "1",
                "-c:a",
                "pcm_s16le",
                str(wav_path),
            ]
        )
        with wave.open(str(wav_path), "rb") as handle:
            segment = np.frombuffer(handle.readframes(handle.getnframes()), dtype=np.int16)
        segment = segment.astype(np.float64) / 32767.0
        nominal = min(len(segment), int((end - start) * SR))
        if overlap and nominal < len(segment):
            fade_len = min(len(segment) - nominal, int(overlap * SR))
            segment[nominal : nominal + fade_len] *= np.cos(
                0.5 * np.pi * np.linspace(0, 1, fade_len, endpoint=False)
            )
        if index and str(selection.get("transition") or "crossfade").lower() != "cut":
            fade_len = min(
                len(segment), int((0.12 if selection.get("transition") == "stinger" else 2.5) * SR)
            )
            if fade_len:
                segment[:fade_len] *= np.sin(
                    0.5 * np.pi * np.linspace(0, 1, fade_len, endpoint=False)
                )
        out_start = int(start * SR)
        out_end = min(total, out_start + len(segment))
        bed[out_start:out_end] += segment[: out_end - out_start]
    if approved_library:
        for index, selection in enumerate(selections):
            transition = selection.get("transition_plan")
            if not (
                index > 0
                and isinstance(transition, dict)
                and transition.get("mode") == "approved_bridge"
            ):
                continue
            bridge_path = Path(str(transition.get("bridge_path") or "")).expanduser().resolve()
            expected_sha = str(transition.get("bridge_sha256") or "")
            if (
                not bridge_path.is_file()
                or bridge_path.is_symlink()
                or len(expected_sha) != 64
                or sha256(bridge_path) != expected_sha
            ):
                raise RenderError("approved transition bridge failed checksum binding")
            duration = min(
                float(transition.get("bridge_duration_sec") or 0.0),
                float(transition.get("duration_sec") or 0.0),
            )
            if duration <= 0:
                raise RenderError("approved transition bridge has invalid duration")
            bridge_wav = work / f"bgm_bridge_{index:03d}.wav"
            run(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    str(bridge_path),
                    "-t",
                    f"{duration:.3f}",
                    "-ar",
                    str(SR),
                    "-ac",
                    "1",
                    "-c:a",
                    "pcm_s16le",
                    str(bridge_wav),
                ]
            )
            with wave.open(str(bridge_wav), "rb") as handle:
                bridge = np.frombuffer(handle.readframes(handle.getnframes()), dtype=np.int16)
            bridge = bridge.astype(np.float64) / 32767.0
            boundary = float(selection.get("start_sec") or 0.0)
            bridge_start = max(0, int((boundary - duration / 2.0) * SR))
            bridge_end = min(total, bridge_start + len(bridge))
            bridge = bridge[: bridge_end - bridge_start]
            if not len(bridge):
                continue
            half = max(1, len(bridge) // 2)
            envelope = np.ones(len(bridge), dtype=np.float64)
            envelope[:half] = np.sin(0.5 * np.pi * np.linspace(0, 1, half, endpoint=False))
            envelope[half:] = np.cos(
                0.5 * np.pi * np.linspace(0, 1, len(bridge) - half, endpoint=False)
            )
            bed[bridge_start:bridge_end] *= 0.45
            bed[bridge_start:bridge_end] += bridge * envelope * 0.9
    return np.clip(bed, -1.0, 1.0), selections


def probe_mixed_loudness(path: Path) -> dict[str, Any] | None:
    """Best-effort integrated loudness via ffmpeg ebur128 (for mix_report / status)."""
    if not path.is_file():
        return None
    proc = run(
        [
            "ffmpeg",
            "-hide_banner",
            "-i",
            str(path),
            "-af",
            "ebur128=framelog=verbose",
            "-f",
            "null",
            "-",
        ],
        check=False,
    )
    text = (proc.stderr or "") + (proc.stdout or "")
    # Typical: "I:         -16.2 LUFS" and "LRA:         5.1 LU" and "Peak:       -1.2 dBFS"
    out: dict[str, Any] = {"ok": False, "source": "ffmpeg_ebur128"}

    m_i = re.search(r"\bI:\s*([+-]?\d+(?:\.\d+)?)\s*LUFS", text)
    m_lra = re.search(r"\bLRA:\s*([+-]?\d+(?:\.\d+)?)\s*LU", text)
    m_peak = re.search(r"\bPeak:\s*([+-]?\d+(?:\.\d+)?)\s*dBFS", text)
    if m_i:
        out["integrated_lufs"] = float(m_i.group(1))
        out["ok"] = True
    if m_lra:
        out["lra"] = float(m_lra.group(1))
    if m_peak:
        out["true_peak_dbfs"] = float(m_peak.group(1))
    # guidance for shortform
    if out.get("integrated_lufs") is not None:
        lu = float(out["integrated_lufs"])
        if lu > -12:
            out["hint"] = "loud — consider lowering music_volume or vo_gain slightly"
        elif lu < -22:
            out["hint"] = "quiet — consider raising music_volume or vo_gain"
        else:
            out["hint"] = "ok for shortform (~-14 to -18 LUFS typical)"
    return out if out.get("ok") else None


def silence_wav(path: Path, duration: float) -> None:
    run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"anullsrc=channel_layout=mono:sample_rate={SR}:duration={duration}",
            str(path),
        ]
    )

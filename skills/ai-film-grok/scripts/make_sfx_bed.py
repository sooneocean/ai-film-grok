#!/usr/bin/env python3
"""Build free procedural BGM + SFX beds for ai-film-grok formal finals.

No third-party sample packs — pure numpy synthesis (royalty-free generative).
"""

from __future__ import annotations

import argparse
import json
import math
import wave
from pathlib import Path

import numpy as np

SR = 44100


def write_wav_stereo(path: Path, samples: np.ndarray, sr: int = SR) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if samples.ndim == 1:
        samples = np.stack([samples, samples], axis=1)
    # float -> int16
    samples = np.clip(samples, -1.0, 1.0)
    pcm = (samples * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(sr)
        handle.writeframes(pcm.tobytes())


def env_adsr(n: int, a=0.01, d=0.05, s=0.7, r=0.1) -> np.ndarray:
    ea, ed, er = int(SR * a), int(SR * d), int(SR * r)
    es = max(0, n - ea - ed - er)
    parts = []
    if ea:
        parts.append(np.linspace(0, 1, ea, endpoint=False))
    if ed:
        parts.append(np.linspace(1, s, ed, endpoint=False))
    if es:
        parts.append(np.full(es, s))
    if er:
        parts.append(np.linspace(s, 0, er, endpoint=False))
    e = np.concatenate(parts) if parts else np.ones(n)
    if len(e) < n:
        e = np.pad(e, (0, n - len(e)))
    return e[:n]


def tone(freq: float, dur: float, amp: float = 0.2, kind: str = "sine") -> np.ndarray:
    n = int(SR * dur)
    t = np.linspace(0, dur, n, endpoint=False)
    if kind == "triangle":
        sig = 2 * np.abs(2 * (t * freq - np.floor(t * freq + 0.5))) - 1
    elif kind == "noise":
        sig = np.random.randn(n) * 0.5
    else:
        sig = np.sin(2 * np.pi * freq * t)
    return amp * sig * env_adsr(n)


def whoosh(dur: float = 0.35, amp: float = 0.25) -> np.ndarray:
    n = int(SR * dur)
    noise = np.random.randn(n)
    # band-ish via cumulative + highpass-ish diff
    sig = np.cumsum(noise)
    sig = sig - np.mean(sig)
    sig = sig / (np.max(np.abs(sig)) + 1e-9)
    # rising filter proxy: multiply by rising envelope and chirp
    t = np.linspace(0, 1, n, endpoint=False)
    chirp = np.sin(2 * np.pi * (400 + 1800 * t) * t * dur)
    e = t * (1 - t) * 4
    return amp * sig * e * 0.6 + amp * 0.4 * chirp * e


def sparkle(amp: float = 0.18) -> np.ndarray:
    parts = [tone(f, 0.08, amp * a, "sine") for f, a in [(1800, 1), (2400, 0.7), (3200, 0.45)]]
    # align lengths
    m = max(len(p) for p in parts)
    acc = np.zeros(m)
    for p in parts:
        acc[: len(p)] += p
    return acc


def _sum_clips(*clips: np.ndarray) -> np.ndarray:
    m = max(len(c) for c in clips)
    out = np.zeros(m)
    for c in clips:
        out[: len(c)] += c
    return out


def soft_hit(amp: float = 0.22) -> np.ndarray:
    return _sum_clips(tone(90, 0.12, amp, "sine") * 0.6, tone(180, 0.1, amp * 0.5, "triangle"))


def footstep(amp: float = 0.15) -> np.ndarray:
    n = int(SR * 0.12)
    noise = np.random.randn(n) * amp
    e = env_adsr(n, 0.002, 0.03, 0.2, 0.08)
    thump = tone(70, 0.1, amp * 0.8)
    return _sum_clips(noise * e, thump)


def giggle_chime(amp: float = 0.12) -> np.ndarray:
    return _sum_clips(tone(880, 0.15, amp), tone(1320, 0.12, amp * 0.6))


def heartbeat(amp: float = 0.12) -> np.ndarray:
    a = tone(55, 0.08, amp)
    b = tone(45, 0.1, amp * 0.9)
    gap = np.zeros(int(SR * 0.12))
    return np.concatenate([a, gap[: int(SR * 0.06)], b])


def classroom_ambience(dur: float, amp: float = 0.04) -> np.ndarray:
    n = int(SR * dur)
    # soft noise bed + distant murmur
    noise = np.random.randn(n) * amp * 0.35
    t = np.linspace(0, dur, n, endpoint=False)
    murmur = amp * 0.25 * np.sin(2 * np.pi * 110 * t) * np.sin(2 * np.pi * 0.35 * t)
    # very slow air AC hum
    hum = amp * 0.15 * np.sin(2 * np.pi * 60 * t)
    return noise + murmur + hum


def _midi(n: float) -> float:
    return 440.0 * (2.0 ** ((n - 69.0) / 12.0))


def rhodes_chord(freqs: list[float], dur: float, amp: float = 0.18) -> np.ndarray:
    """Soft electric-piano / Rhodes-ish: sine + slight bell overtone + tremolo."""
    n = int(SR * dur)
    t = np.linspace(0, dur, n, endpoint=False)
    sig = np.zeros(n)
    trem = 0.82 + 0.18 * np.sin(2 * np.pi * 5.2 * t)
    attack = np.minimum(1.0, t / 0.035)
    release = np.ones(n)
    rel_n = int(SR * min(0.45, dur * 0.25))
    if rel_n > 1:
        release[-rel_n:] = np.linspace(1, 0.15, rel_n)
    env = attack * release
    for i, f in enumerate(freqs):
        w = 1.0 / (1.0 + 0.35 * i)
        fund = np.sin(2 * np.pi * f * t)
        # bell-ish 2nd / 4th partials (Rhodes character)
        bell = 0.28 * np.sin(2 * np.pi * f * 2.01 * t) * np.exp(-2.8 * t)
        bell += 0.12 * np.sin(2 * np.pi * f * 4.02 * t) * np.exp(-4.5 * t)
        sig += w * (fund + bell)
    return amp * sig * trem * env / max(len(freqs), 1)


def kick_drum(amp: float = 0.35) -> np.ndarray:
    n = int(SR * 0.22)
    t = np.linspace(0, 0.22, n, endpoint=False)
    # pitch drop 120→45 Hz
    phase = 2 * np.pi * (120 * t - 170 * t * t)
    body = np.sin(phase) * np.exp(-14 * t)
    click = np.random.randn(n) * 0.08 * np.exp(-80 * t)
    return amp * (body + click)


def soft_clap(amp: float = 0.18) -> np.ndarray:
    n = int(SR * 0.12)
    noise = np.random.randn(n)
    e = np.exp(-np.linspace(0, 35, n))
    # band-ish: highpass via diff
    noise = np.diff(noise, prepend=noise[0])
    noise = noise / (np.max(np.abs(noise)) + 1e-9)
    return amp * noise * e


def soft_hat(amp: float = 0.06, open_: bool = False) -> np.ndarray:
    dur = 0.08 if not open_ else 0.18
    n = int(SR * dur)
    noise = np.random.randn(n)
    # brighten
    noise = np.diff(noise, prepend=0)
    noise = noise / (np.max(np.abs(noise)) + 1e-9)
    decay = 28 if not open_ else 12
    e = np.exp(-np.linspace(0, decay, n))
    return amp * noise * e


def _rnb_progressions() -> list[dict[str, object]]:
    """Several intimate late-night progressions (anti-loop: not one Am forever)."""
    return [
        {
            "name": "am_intimate",
            "chords": [
                [_midi(57), _midi(60), _midi(64), _midi(67), _midi(71)],  # Am9
                [_midi(50), _midi(53), _midi(57), _midi(60), _midi(64)],  # Dm9
                [_midi(55), _midi(59), _midi(62), _midi(65), _midi(64)],  # G13
                [_midi(48), _midi(52), _midi(55), _midi(59), _midi(62)],  # Cmaj9
            ],
            "bass": [_midi(33), _midi(38), _midi(43), _midi(36)],
        },
        {
            "name": "em_velvet",
            "chords": [
                [_midi(52), _midi(55), _midi(59), _midi(62), _midi(66)],  # Em9
                [_midi(45), _midi(48), _midi(52), _midi(55), _midi(59)],  # Am9 low
                [_midi(50), _midi(54), _midi(57), _midi(60), _midi(64)],  # D9
                [_midi(47), _midi(51), _midi(54), _midi(57), _midi(61)],  # B7sus-ish
            ],
            "bass": [_midi(28), _midi(33), _midi(38), _midi(35)],
        },
        {
            "name": "fm_late",
            "chords": [
                [_midi(53), _midi(56), _midi(60), _midi(63), _midi(67)],  # Fm9
                [_midi(48), _midi(51), _midi(55), _midi(58), _midi(62)],  # Cm9
                [_midi(51), _midi(55), _midi(58), _midi(61), _midi(65)],  # Ebm add
                [_midi(46), _midi(50), _midi(53), _midi(56), _midi(60)],  # Bbmaj9
            ],
            "bass": [_midi(29), _midi(36), _midi(39), _midi(34)],
        },
        {
            "name": "gm_soft",
            "chords": [
                [_midi(55), _midi(58), _midi(62), _midi(65), _midi(69)],  # Gm9
                [_midi(48), _midi(51), _midi(55), _midi(58), _midi(62)],  # Cm9
                [_midi(53), _midi(57), _midi(60), _midi(63), _midi(67)],  # F9
                [_midi(50), _midi(53), _midi(57), _midi(60), _midi(64)],  # Dm
            ],
            "bass": [_midi(31), _midi(36), _midi(41), _midi(38)],
        },
        {
            "name": "db_smoke",
            "chords": [
                [_midi(49), _midi(53), _midi(56), _midi(60), _midi(63)],  # Dbmaj9
                [_midi(54), _midi(58), _midi(61), _midi(65), _midi(68)],  # Gbmaj9
                [_midi(51), _midi(54), _midi(58), _midi(61), _midi(65)],  # Ebm9
                [_midi(56), _midi(60), _midi(63), _midi(67), _midi(70)],  # Ab13
            ],
            "bass": [_midi(25), _midi(30), _midi(27), _midi(32)],
        },
        {
            "name": "bm_neon",
            "chords": [
                [_midi(59), _midi(62), _midi(66), _midi(69), _midi(73)],  # Bm9
                [_midi(52), _midi(55), _midi(59), _midi(62), _midi(66)],  # Em9
                [_midi(57), _midi(61), _midi(64), _midi(67), _midi(71)],  # A9
                [_midi(54), _midi(58), _midi(61), _midi(64), _midi(68)],  # F#m
            ],
            "bass": [_midi(35), _midi(28), _midi(33), _midi(30)],
        },
    ]


# Procedural bed styles (v3 anti-fatigue): seed picks one so takes don't share timbre family.
RNB_STYLES = ("velvet", "pulse", "ambient", "lofi", "glitter")


def pick_rnb_style(seed: int | None) -> str:
    if seed is None:
        return "velvet"
    return RNB_STYLES[int(seed) % len(RNB_STYLES)]


def _style_params(style: str, rng: np.random.Generator, bpm_in: float) -> dict[str, object]:
    """Per-style sonic fingerprint — different enough that seed change is audible."""
    s = (style or "velvet").lower()
    if s == "pulse":
        return {
            "bpm": float(bpm_in) * float(rng.uniform(1.08, 1.18)),  # ~82–90
            "pad_mix": 0.28,
            "rhodes_mix": 0.45,
            "kit_scale": 1.25,
            "sub_scale": 1.15,
            "air": 0.008,
            "lofi": False,
            "bright": 0.0,
            "swing": 0.0,
            "sections": [
                (0.40, 0.55, 0.70, 0.85, False),
                (0.35, 0.70, 1.00, 1.00, False),
                (0.55, 0.40, 0.85, 0.90, False),
                (0.30, 0.60, 0.75, 0.95, True),
                (0.35, 0.50, 0.90, 0.85, False),
                (0.25, 0.30, 0.45, 0.60, True),
            ],
            "kit_pattern": "four_on",
        }
    if s == "ambient":
        return {
            "bpm": float(bpm_in) * float(rng.uniform(0.82, 0.92)),  # ~62–70
            "pad_mix": 0.95,
            "rhodes_mix": 0.22,
            "kit_scale": 0.18,
            "sub_scale": 0.55,
            "air": 0.022,
            "lofi": False,
            "bright": 0.0,
            "swing": 0.0,
            "sections": [
                (1.00, 0.15, 0.05, 0.45, True),
                (0.90, 0.30, 0.12, 0.50, True),
                (1.00, 0.20, 0.08, 0.40, True),
                (0.85, 0.35, 0.15, 0.55, True),
                (0.95, 0.25, 0.10, 0.45, True),
                (0.70, 0.15, 0.05, 0.35, True),
            ],
            "kit_pattern": "sparse",
        }
    if s == "lofi":
        return {
            "bpm": float(bpm_in) * float(rng.uniform(0.90, 0.98)),
            "pad_mix": 0.55,
            "rhodes_mix": 0.70,
            "kit_scale": 0.75,
            "sub_scale": 0.80,
            "air": 0.035,
            "lofi": True,
            "bright": -0.35,
            "swing": 0.12,
            "sections": [
                (0.70, 0.55, 0.35, 0.60, False),
                (0.50, 0.80, 0.70, 0.75, False),
                (0.85, 0.35, 0.25, 0.50, True),
                (0.45, 0.75, 0.55, 0.70, False),
                (0.60, 0.50, 0.40, 0.55, False),
                (0.50, 0.30, 0.20, 0.40, True),
            ],
            "kit_pattern": "swung",
        }
    if s == "glitter":
        return {
            "bpm": float(bpm_in) * float(rng.uniform(0.95, 1.05)),
            "pad_mix": 0.45,
            "rhodes_mix": 0.90,
            "kit_scale": 0.65,
            "sub_scale": 0.70,
            "air": 0.015,
            "lofi": False,
            "bright": 0.45,
            "swing": 0.0,
            "sections": [
                (0.60, 0.70, 0.30, 0.50, False),
                (0.45, 1.00, 0.55, 0.70, False),
                (0.80, 0.40, 0.20, 0.45, False),
                (0.40, 0.85, 0.45, 0.65, True),
                (0.55, 0.75, 0.50, 0.60, False),
                (0.50, 0.40, 0.20, 0.40, True),
            ],
            "kit_pattern": "open_hat",
        }
    # velvet (default intimate)
    return {
        "bpm": float(bpm_in) * float(rng.uniform(0.97, 1.03)),
        "pad_mix": 0.50,
        "rhodes_mix": 0.55,
        "kit_scale": 1.0,
        "sub_scale": 1.0,
        "air": 0.012,
        "lofi": False,
        "bright": 0.0,
        "swing": 0.0,
        "sections": [
            (0.75, 0.35, 0.25, 0.55, False),
            (0.55, 0.85, 0.85, 0.85, False),
            (0.95, 0.25, 0.15, 0.40, False),
            (0.50, 0.70, 0.55, 0.75, True),
            (0.70, 0.55, 0.40, 0.60, False),
            (0.45, 0.30, 0.20, 0.45, True),
        ],
        "kit_pattern": "classic",
    }


def _one_pole_lowpass(sig: np.ndarray, cutoff_hz: float, sr: int = SR) -> np.ndarray:
    """Cheap lowpass for lofi muffling (stable one-pole, numpy lfilter-style)."""
    if len(sig) == 0:
        return sig
    # y[n] = (1-a)*x[n] + a*y[n-1]  via recursive; use scipy-free chunk approx:
    # multi-tap moving average as spectral stand-in when pure loop would be too slow
    a = float(np.exp(-2.0 * math.pi * max(40.0, cutoff_hz) / sr))
    # vectorized IIR via iterative blocks (keeps state, O(n) in C via numpy accumulate trick)
    # geometric EMA: use numba-free recurrence in float64 with np.copy + stride trick
    y = np.empty_like(sig, dtype=np.float64)
    y[0] = sig[0]
    # For long audio, pure Python is too slow — use FIR-ish box + light EMA hybrid
    win = max(3, int(sr / max(cutoff_hz, 80.0)))
    if win % 2 == 0:
        win += 1
    kernel = np.ones(win, dtype=np.float64) / win
    sm = np.convolve(sig.astype(np.float64), kernel, mode="same")
    # blend with original for less mush
    return (1.0 - a) * sm + a * sig.astype(np.float64)


def rnb_bgm(
    dur: float,
    amp: float = 0.18,
    bpm: float = 76.0,
    *,
    seed: int | None = None,
    style: str | None = None,
) -> np.ndarray:
    """Seductive late-night R&B with anti-fatigue arrangement (v3 multi-style).

    Why rewrites:
      2026-07-20: fixed Am loop → multi progression + sections + seed
      2026-07-21: seed alone still same timbre → **style family** from seed
        (velvet|pulse|ambient|lofi|glitter) so takes sound different, not just reordered
    """
    seed_i = None if seed is None else int(seed) & 0x7FFFFFFF
    rng = np.random.default_rng(seed_i)
    if seed_i is not None:
        np.random.seed(seed_i)
    style_s = (style or pick_rnb_style(seed_i)).lower()
    if style_s not in RNB_STYLES:
        style_s = "velvet"
    sp = _style_params(style_s, rng, bpm)
    bpm = float(sp["bpm"])
    n = int(SR * dur)
    t = np.linspace(0, dur, n, endpoint=False)
    mono = np.zeros(n)
    beat = 60.0 / bpm
    bar = beat * 4
    chord_dur = bar * 2  # 2 bars / chord

    progs = _rnb_progressions()
    order = list(range(len(progs)))
    rng.shuffle(order)

    sections: list[tuple[float, float, float, float, bool]] = list(sp["sections"])  # type: ignore[arg-type]
    sec_len = max(bar * 4, dur / max(len(sections), 1))

    def _section_at(sec: float) -> tuple[float, float, float, float, bool]:
        idx = min(len(sections) - 1, int(sec / sec_len))
        return sections[idx]

    pad_mix = float(sp["pad_mix"])
    rhodes_mix = float(sp["rhodes_mix"])
    kit_scale = float(sp["kit_scale"])
    sub_scale = float(sp["sub_scale"])
    air_amp = float(sp["air"])
    bright = float(sp["bright"])
    swing = float(sp["swing"])
    kit_pattern = str(sp["kit_pattern"])
    do_lofi = bool(sp["lofi"])

    # --- pad (style-dependent partial set) ---
    if style_s == "glitter":
        base_pads = [123.47, 196.0, 246.94, 311.13, 392.0, 493.88]
    elif style_s == "ambient":
        base_pads = [65.41, 98.0, 130.81, 164.81, 196.0, 246.94]
    elif style_s == "pulse":
        base_pads = [82.41, 110.0, 146.83, 164.81]
    else:
        base_pads = [98.0, 146.83, 196.0, 246.94, 293.66]
    pad = np.zeros(n)
    for i, f0 in enumerate(base_pads):
        det = 1.0 + 0.004 * np.sin(2 * np.pi * (0.07 + 0.015 * i) * t + rng.uniform(0, 6))
        f1 = f0 * float(rng.choice([0.75, 1.0, 1.5]))
        morph = 0.5 + 0.5 * np.sin(2 * np.pi * (0.03 + 0.01 * i) * t + i)
        f = f0 * (1 - morph) + f1 * morph
        pad += (0.16 / len(base_pads)) * np.sin(2 * np.pi * f * det * t)
        if bright > 0 and i >= len(base_pads) // 2:
            pad += (0.06 * bright / len(base_pads)) * np.sin(2 * np.pi * f * 2.01 * det * t)
    pad_lfo = 0.5 + 0.5 * np.sin(2 * np.pi * (0.5 / max(bar * 6, 1)) * t)
    pad_levels = np.array([s[0] for s in sections], dtype=np.float64)
    sec_idx = np.minimum(len(sections) - 1, (t / max(sec_len, 1e-6)).astype(np.int32))
    pad_gain = pad_levels[sec_idx]
    mono += pad_mix * amp * pad * (0.55 + 0.45 * pad_lfo) * pad_gain

    # --- chord hits + sub ---
    t0 = 0.0
    ci = 0
    prog_i = 0
    while t0 < dur:
        if ci > 0 and ci % 4 == 0:
            prog_i = (prog_i + 1) % len(order)
        prog = progs[order[prog_i]]
        chords = prog["chords"]  # type: ignore[assignment]
        bass_roots = prog["bass"]  # type: ignore[assignment]
        assert isinstance(chords, list) and isinstance(bass_roots, list)
        freqs = list(chords[ci % len(chords)])
        if rng.random() < 0.22 and len(freqs) >= 2:
            freqs[0] *= 0.5
        root = float(bass_roots[ci % len(bass_roots)])
        cdur = min(chord_dur, dur - t0 + 0.05)
        _, rh_g, _, sub_g, _ = _section_at(t0)
        ch = rhodes_chord(freqs, cdur, amp=rhodes_mix * amp * rh_g)
        ch *= float(rng.uniform(0.88, 1.08))
        i0 = int(t0 * SR)
        i1 = min(n, i0 + len(ch))
        mono[i0:i1] += ch[: i1 - i0]

        bn = i1 - i0
        if bn > 0:
            bt = np.linspace(0, bn / SR, bn, endpoint=False)
            glide = np.minimum(1.0, bt / 0.08)
            f_start = root * float(rng.uniform(0.92, 0.97))
            f_now = f_start + (root - f_start) * glide
            phase = np.cumsum(2 * np.pi * f_now / SR)
            sub = 0.40 * amp * sub_scale * sub_g * np.sin(phase)
            sub += 0.10 * amp * sub_scale * sub_g * np.sin(2 * phase)
            pumps = np.ones(bn)
            step = int(beat * SR)
            for k in range(0, bn, max(1, step)):
                kn = min(int(0.18 * SR), bn - k)
                if kn > 0:
                    pumps[k : k + kn] *= np.linspace(0.32, 1.0, kn)
            mono[i0:i1] += sub * pumps * np.minimum(1.0, bt / 0.02)

        t0 += chord_dur
        ci += 1

    # --- drum kit ---
    kick = kick_drum(0.28 * amp / 0.18 * kit_scale)
    clap = soft_clap(0.14 * amp / 0.18 * kit_scale)
    hat = soft_hat(0.045 * amp / 0.18 * kit_scale, open_=False)
    hat_o = soft_hat(0.035 * amp / 0.18 * kit_scale, open_=True)

    def _add(at_s: float, clip: np.ndarray, gain: float = 1.0) -> None:
        if gain <= 0 or at_s >= dur:
            return
        ii0 = int(at_s * SR)
        if ii0 >= n:
            return
        ii1 = min(n, ii0 + len(clip))
        span = ii1 - ii0
        if span <= 0:
            return
        mono[ii0:ii1] += clip[:span] * gain

    beat_i = 0
    while beat_i * beat < dur:
        at = beat_i * beat
        # swing offset on even 8ths
        swing_off = swing * beat * 0.5 if (beat_i % 2 == 1 and swing > 0) else 0.0
        at_sw = at + swing_off
        _, _, kit_g, _, half = _section_at(at)
        kit_g *= kit_scale
        if kit_g < 0.06:
            beat_i += 1
            continue

        if kit_pattern == "sparse" or half:
            if beat_i % 4 == 0:
                _add(at_sw, kick, kit_g)
            if beat_i % 8 == 4:
                _add(at_sw, clap, 0.55 * kit_g)
            if beat_i % 2 == 0:
                _add(at_sw, hat, 0.35 * kit_g)
        elif kit_pattern == "four_on":
            _add(at_sw, kick, kit_g * (0.9 if beat_i % 4 == 0 else 0.75))
            if beat_i % 4 in (1, 3):
                _add(at_sw, clap, 0.9 * kit_g)
            for half_b in (0.0, 0.5):
                _add(at + half_b * beat + (swing * beat * 0.25 if half_b else 0), hat, 0.7 * kit_g)
        elif kit_pattern == "open_hat":
            if beat_i % 4 in (0, 2):
                _add(at_sw, kick, kit_g * 0.85)
            if beat_i % 4 in (1, 3):
                _add(at_sw, clap, 0.7 * kit_g)
            _add(at_sw, hat_o if beat_i % 2 == 0 else hat, 0.85 * kit_g)
            if beat_i % 4 == 3:
                _add(at + 0.5 * beat, hat_o, 0.6 * kit_g)
        else:
            # classic / swung
            if half:
                if beat_i % 4 == 0:
                    _add(at_sw, kick, kit_g)
                if beat_i % 4 == 2:
                    _add(at_sw, clap, 0.7 * kit_g)
                _add(at_sw, hat, 0.55 * kit_g)
            else:
                if beat_i % 4 in (0, 2):
                    _add(at_sw, kick, kit_g)
                    if beat_i % 4 == 2 and rng.random() < 0.18:
                        _add(at + 0.5 * beat, kick, 0.35 * kit_g)
                if beat_i % 4 in (1, 3):
                    _add(at_sw, clap, 0.85 * kit_g)
                for half_b in (0.0, 0.5):
                    ht = at + half_b * beat + (swing * beat * 0.25 if half_b else 0)
                    if ht >= dur:
                        break
                    h = hat_o if (beat_i % 4 == 3 and half_b == 0.5) else hat
                    if kit_g < 0.5 and half_b == 0.5 and rng.random() < 0.4:
                        continue
                    _add(ht, h, kit_g)
                if beat_i % 16 == 15 and rng.random() < 0.65:
                    for k in range(4):
                        _add(at + (k / 4.0) * beat, hat, 0.9 * kit_g)
        beat_i += 1

    # glitter chime accents
    if style_s == "glitter":
        for sec in np.arange(bar * 2, dur, bar * 4):
            if rng.random() < 0.7:
                _add(float(sec), sparkle(0.10 * amp), 1.0)

    # air / vinyl
    mono += air_amp * amp * rng.standard_normal(n) * (0.5 + 0.5 * np.sin(2 * np.pi * 0.07 * t))
    if do_lofi:
        mono = _one_pole_lowpass(mono, cutoff_hz=float(rng.uniform(2800, 4200)))
        # light wow (slow pitch-ish amplitude)
        mono *= 0.92 + 0.08 * np.sin(2 * np.pi * 0.35 * t + rng.uniform(0, 3))

    out = np.tanh(mono * 1.12)
    if bright < 0:
        out = _one_pole_lowpass(out, cutoff_hz=5000 + 3000 * (1 + bright))
    fade_in = int(SR * 0.35)
    fade_out = int(SR * 1.2)
    if n > fade_in + fade_out:
        out[:fade_in] *= np.linspace(0, 1, fade_in)
        out[-fade_out:] *= np.linspace(1, 0, fade_out)
    peak = float(np.max(np.abs(out)) + 1e-9)
    if peak > 0.98:
        out *= 0.98 / peak
    # stash last style for callers that care (module-level, not thread-safe — fine for CLI)
    global _LAST_RNB_STYLE
    _LAST_RNB_STYLE = style_s
    return out


_LAST_RNB_STYLE: str = "velvet"


def last_rnb_style() -> str:
    return _LAST_RNB_STYLE


def sensual_bgm(dur: float, amp: float = 0.16, *, seed: int | None = None) -> np.ndarray:
    """Alias: seductive R&B is the default sensual bed."""
    return rnb_bgm(dur, amp=amp, bpm=76.0, seed=seed)


def place(base: np.ndarray, clip: np.ndarray, at: float, pan: float = 0.0) -> None:
    i0 = int(at * SR)
    i1 = i0 + len(clip)
    if i0 >= len(base):
        return
    if i1 > len(base):
        clip = clip[: len(base) - i0]
        i1 = len(base)
    if clip.ndim == 1:
        left = clip * math.cos((pan + 1) * 0.25 * math.pi)
        right = clip * math.sin((pan + 1) * 0.25 * math.pi)
        base[i0:i1, 0] += left
        base[i0:i1, 1] += right
    else:
        base[i0:i1] += clip


def build_bed(
    duration: float,
    shot_starts: list[float],
    *,
    mood: str = "rnb",
    sfx_level: float = 0.9,
    bpm: float = 76.0,
    seed: int | None = None,
) -> np.ndarray:
    n = int(SR * duration)
    bed = np.zeros((n, 2), dtype=np.float64)

    mood = (mood or "rnb").lower()
    # BGM: seductive R&B is default for 色气 / storyteller
    if mood in ("rnb", "r&b", "sensual", "seductive", "ecchi", "soul"):
        bgm = rnb_bgm(duration, amp=0.17, bpm=bpm, seed=seed)
        # light room air only — classroom murmur fights R&B
        amb = classroom_ambience(duration, amp=0.012)
    elif mood == "dark":
        bgm = rnb_bgm(duration, amp=0.14, bpm=68.0, seed=seed)
        amb = classroom_ambience(duration, amp=0.02)
    else:
        bgm = rnb_bgm(duration, amp=0.13, bpm=82.0, seed=seed)
        amb = classroom_ambience(duration, amp=0.03)

    place(bed, amb, 0.0)
    place(bed, bgm, 0.0)

    # per-shot SFX — keep light so R&B groove stays sexy, not busy
    sfx_scale = 0.65 * sfx_level
    for i, t0 in enumerate(shot_starts):
        place(bed, whoosh(0.24, 0.10 * sfx_scale), max(0.0, t0 - 0.10), pan=(-0.25 if i % 2 == 0 else 0.25))
        place(bed, soft_hit(0.09 * sfx_scale), t0 + 0.02)
        if i in (0, 5):
            place(bed, sparkle(0.09 * sfx_scale), t0 + 0.4)
        if i in (2, 4):
            place(bed, heartbeat(0.08 * sfx_scale), t0 + 1.8)
        if i == 5:
            place(bed, heartbeat(0.10 * sfx_scale), t0 + 1.2)

    # gentle limiter
    peak = np.max(np.abs(bed)) + 1e-9
    if peak > 0.95:
        bed *= 0.95 / peak
    return bed


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--duration", type=float, required=True)
    ap.add_argument("--shot-starts", type=str, required=True, help="comma-separated seconds")
    ap.add_argument("--out", required=True)
    ap.add_argument("--mood", default="rnb", help="rnb|sensual|dark|playful — 色气片默认 rnb")
    ap.add_argument("--sfx-level", type=float, default=0.9)
    ap.add_argument("--bpm", type=float, default=76.0, help="R&B tempo, ~72-80 seductive")
    ap.add_argument("--seed", type=int, default=None, help="BGM RNG seed (anti-fatigue variety / style)")
    args = ap.parse_args()
    starts = [float(x) for x in args.shot_starts.split(",") if x.strip()]
    bed = build_bed(
        args.duration,
        starts,
        mood=args.mood,
        sfx_level=args.sfx_level,
        bpm=args.bpm,
        seed=args.seed,
    )
    write_wav_stereo(Path(args.out), bed)
    print(
        json.dumps(
            {
                "ok": True,
                "out": args.out,
                "duration": args.duration,
                "shots": len(starts),
                "mood": args.mood,
                "bpm": args.bpm,
                "seed": args.seed,
                "style": last_rnb_style() if args.seed is not None else None,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

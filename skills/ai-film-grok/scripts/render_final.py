#!/usr/bin/env python3
"""Render a formal final film: edge-tts VO + optional lip-sync + BGM + PIL subs + FFmpeg.

Adapted from ai-film-codex postproduction (render_motion_film / make_v6 patterns)
for ai-film-grok local manifests and Grok I2V clips.

Lip-sync stage (optional): after VO, retime talking faces with MuseTalk/Wav2Lip/external
so mouth matches 口白 — see references/lipsync.md.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import wave
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
from edit_policy import (
    DEFAULT_TRANSITION_SEC,
    PolicyError,
    build_acrossfade_filter_graph,
    build_xfade_filter_graph,
    expand_story_join_intents,
    expand_story_join_styles,
    film_segment_timeline,
    normalize_transition_sec,
    plan_stretch,
)
from film_spec import FilmSpecError, validate_film_spec
from media_qa import MediaQAError, analyze_media, approved_clip_record
from PIL import Image, ImageDraw, ImageFont
from runtime_policy import sha256
from security_policy import (
    SecurityPolicyError,
    atomic_write_text,
    minimal_subprocess_env,
    reject_symlinks,
    safe_existing_file,
    safe_output_path,
    safe_workspace_directory,
)
from sound_plan import (
    SoundPlanError,
    apply_mute_windows_to_samples,
    apply_sfx_accents_to_samples,
    build_mood_timeline,
    expand_sound_events,
    inject_auto_sfx_if_empty,
    resolve_loudnorm,
    resolve_music_template,
    resolve_sidechain,
    should_apply_loudnorm,
    sidechain_filter_fragment,
    validate_audio_tracks_contract,
)

# local sibling import
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from lipsync_backend import lipsync_one, should_lipsync_shot
    from lipsync_backend import probe as lipsync_probe
except ImportError:  # pragma: no cover
    lipsync_one = None  # type: ignore
    should_lipsync_shot = None  # type: ignore
    lipsync_probe = None  # type: ignore

try:
    from tts_backend import probe as tts_probe
    from tts_backend import synthesize as tts_synthesize
except ImportError:  # pragma: no cover
    tts_synthesize = None  # type: ignore
    tts_probe = None  # type: ignore

try:
    from voice_tracks import (
        compute_color_offset_sec,
        resolve_shot_vocal_color,
        resolve_voice_tracks,
        sound_cues_to_sfx_kinds,
    )
except ImportError:  # pragma: no cover
    compute_color_offset_sec = None  # type: ignore
    resolve_shot_vocal_color = None  # type: ignore
    resolve_voice_tracks = None  # type: ignore
    sound_cues_to_sfx_kinds = None  # type: ignore

# 中文女声优先：旁白是主叙事，必须压过 BGM
# TTS 质量与稳定声线分开选择；跨服务商降级必须显式开启。
DEFAULT_VOICE = "zh-CN-XiaoxiaoNeural"  # edge 显式后端默认女声
STORYTELLER_VOICE = "zh-CN-XiaoxiaoNeural"
# P0 · 2026-07-23: character dialogue defaults to Japanese edge voices
HEROINE_JA_VOICE = "ja-JP-NanamiNeural"
PARTNER_JA_VOICE = "ja-JP-KeitaNeural"
_NARRATOR_SPEAKERS = frozenset({"storyteller", "narrator", "vo", "旁白", "os", "inner", "内心"})
_HEROINE_SPEAKERS = frozenset(
    {"heroine", "female", "fufu", "girl", "woman", "she", "女主", "沈筱", "astra"}
)
_PARTNER_SPEAKERS = frozenset(
    {"partner", "male_hero", "hero", "male", "boy", "man", "he", "男主", "杨舟"}
)


def build_post_enhancement_vf_chain(
    enable_denoise: bool = True,
    enable_sharpen: bool = True,
    denoise_strength: str = "2.0:1.5:3.0:2.5",
    sharpen_strength: float = 0.35,
) -> str:
    """Build FFmpeg video filter chain for 3D temporal denoising and CAS sharpening."""
    filters = []
    if enable_denoise:
        filters.append(f"hqdn3d={denoise_strength}")
    if enable_sharpen:
        filters.append(f"cas=strength={sharpen_strength:.2f}")
    return ",".join(filters)


# 混音：旁白永远是主角
# Multi-track mix (旁白 / 娇喘语助 / 原生 clip 音 / BGM 独立增益):
# - BGM 生成用固定健康 amp（不吃 music_volume，避免「生成压一次 + 混音再压一次」→ 音乐消失）
# - music_volume 只在 amix 时用；sidechain 说话时让路，停顿时音乐回来
# - vocal_color = 色气语助词/娇喘，独立 TTS 轨，不写进 nar（见 voice-tracks.md）
DEFAULT_MUSIC_VOLUME = 0.48  # 略降 BGM，旁白更贴耳、节奏更干净
DEFAULT_BGM_GEN_AMP = 0.22  # 程序化 BGM 生成响度（固定，勿再乘 music_volume）
DEFAULT_VO_GAIN = 1.32  # 旁白增益：清晰压过环境音与 BGM（星声 lesson 略抬）
DEFAULT_VOCAL_COLOR_GAIN = 0.0  # 2026-07-21: 语助轨默认关闭；成片以 nar+BGM 主导
DEFAULT_VO_RATE = "+0%"  # 默认不拖腔；快节奏色气短片可用 +5%~+8%（禁 -3%+slot 叠拖）
DEFAULT_VO_PITCH = "+0Hz"
FONT_CANDIDATES = [
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/PingFang.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
]
# Re-export policy constants for tests/back-compat
# Transitions: DEFAULT_TRANSITION_SEC from edit_policy (silk soft dissolve)
SR = 44100
# 9:16 竖屏：一句一卡；过长句按逗号拆开，阅读更轻松
DEFAULT_SUB_MAX_CHARS = 12  # phrase-sized cue; long nar always splits at ，/。


class RenderError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def write_json(path: Path, value: dict[str, Any]) -> None:
    atomic_write_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    argv = list(cmd)
    executable = Path(argv[0]).name if argv else ""
    if executable == "ffmpeg" and "-nostdin" not in argv:
        argv.insert(1, "-nostdin")
    # P0 · 2026-07-23: complex sidechain mix on ~60–90s films can exceed 600s wall
    # (TimeoutExpired mid-plate). Override with AIFILM_FFMPEG_TIMEOUT seconds.
    if executable == "ffmpeg":
        try:
            ff_timeout = float(os.environ.get("AIFILM_FFMPEG_TIMEOUT") or 1800)
        except (TypeError, ValueError):
            ff_timeout = 1800.0
        ff_timeout = max(120.0, ff_timeout)
    else:
        ff_timeout = 60.0
    return subprocess.run(
        argv,
        timeout=ff_timeout,
        check=check,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        env=minimal_subprocess_env(),
    )


def pdur(path: Path | str) -> float:
    """Fail-loud duration probe — never invent silent defaults on missing media."""
    try:
        from media_duration import MediaDurationError, probe_duration_sec
    except ImportError:
        # Fallback if module missing: still fail loud on empty/missing
        p = Path(path)
        if not p.is_file():
            raise RenderError(f"media missing for duration probe: {p}") from None
        result = run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=nokey=1:noprint_wrappers=1",
                str(path),
            ]
        )
        raw = (result.stdout or "").strip()
        if not raw:
            raise RenderError(f"unreadable duration (empty ffprobe): {path}") from None
        return float(raw)
    try:
        return probe_duration_sec(path, label="render_final")
    except MediaDurationError as exc:
        raise RenderError(str(exc)) from exc


def resolve_font() -> str:
    for path in FONT_CANDIDATES:
        if Path(path).is_file():
            return path
    raise RenderError("No Chinese-capable system font found")


def split_units(text: str, max_len: int = 12) -> list[str]:
    """Chinese subtitle units: **one short phrase per cue** for 9:16 HF captions.

    Prefer natural clause boundaries (。！？ and ，、) so long storyteller nars
    become readable one-liners — never dump a full 20–30 char shot nar in one card.

    Hard cap: no unit longer than max_len (trailing ，。… may make it max_len+1).
    """
    text = (text or "").strip()
    if not text:
        return []
    text = text.replace("……", "…").replace("...", "…")
    # Normalize multi-dash so we split once after the whole dash run
    text = re.sub(r"[—–-]{2,}", "——", text)
    # Phrase-first: strong end + comma/顿号; keep —— as a single end marker
    # (user: 一句話一個字幕；太長字串要拆開)
    segs = re.split(r"(?<=[。！？!?；;…，,、])|(?<=——)", text)
    units: list[str] = []
    soft_particles = "的了着过吗呢吧啊哦喔与和是在把被给让"

    def flush(buf: str) -> None:
        buf = buf.strip(" \t")
        # keep trailing ，。 for natural reading; strip only spaces
        buf = buf.strip()
        if buf:
            units.append(buf)

    def hard_wrap(part: str) -> None:
        """Wrap long phrase at soft boundaries; never keep a >max_len blob."""
        if len(part) <= max_len:
            flush(part)
            return
        # If only over by a single trailing punct, keep as one card
        if len(part) == max_len + 1 and part[-1] in "，。！？…、,.;!?—":
            flush(part)
            return
        i = 0
        while i < len(part):
            remain = part[i:]
            if len(remain) <= max_len:
                flush(remain)
                break
            if len(remain) == max_len + 1 and remain[-1] in "，。！？…、,.;!?—":
                flush(remain)
                break
            # Search soft cut only inside first max_len chars (not past the hard cap)
            window = remain[:max_len]
            cut = None
            for j, ch in enumerate(window):
                if j < 3:
                    continue
                if ch in "，,、；;…—：:":
                    cut = j + 1
            if cut is None:
                for j in range(len(window) - 1, 2, -1):
                    if window[j] in soft_particles:
                        cut = j + 1
                        break
            if cut is None or cut < 3:
                cut = max_len
            # Avoid 1–2 char tails: leave ≥3 chars for the rest when possible
            rest_len = len(remain) - cut
            if 0 < rest_len < 3 and len(remain) > max_len:
                cut = max(3, min(max_len, len(remain) - 3))
            chunk = remain[:cut]
            # Never emit oversize chunk
            if len(chunk) > max_len:
                chunk = remain[:max_len]
            flush(chunk)
            i += len(chunk)

    for seg in segs:
        seg = seg.strip()
        if not seg:
            continue
        if len(seg) <= max_len:
            flush(seg)
            continue
        # Long clause: split on colon / full-width dash run, then hard wrap
        parts = re.split(r"(?<=[：:])|(?<=——)", seg)
        for part in parts:
            part = part.strip()
            if not part:
                continue
            if len(part) <= max_len:
                flush(part)
            else:
                hard_wrap(part)

    # Only merge accidental 1–2 char orphans — never re-glue past max_len
    merged: list[str] = []
    for u in units:
        if (
            merged
            and len(u) <= 2
            and len(merged[-1]) + len(u) <= max_len
            or merged
            and len(merged[-1]) <= 2
            and len(merged[-1]) + len(u) <= max_len
        ):
            merged[-1] = merged[-1] + u
        else:
            merged.append(u)
    # Drop punctuation-only noise (comma / dash crumbs)
    cleaned = [u.strip(" \t") for u in merged if u.strip(" \t，,、—–-…")]
    # Safety net: re-hard-wrap any unit still over max_len (should be rare)
    final: list[str] = []
    for u in cleaned:
        if len(u) <= max_len:
            final.append(u)
        else:
            # allow single trailing punct beyond max_len
            if len(u) == max_len + 1 and u[-1] in "，。！？…、,.;!?——":
                final.append(u)
            else:
                k = 0
                while k < len(u):
                    final.append(u[k : k + max_len])
                    k += max_len
    return final or [text[:max_len]]


def _split_one_soft(u: str) -> tuple[str, str] | None:
    """Split one line near the middle at a soft boundary; None if too short."""
    if len(u) < 8:
        return None
    mid = len(u) // 2
    best = None
    best_score = 10**9
    for i, ch in enumerate(u):
        if i < 3 or i > len(u) - 3:
            continue
        score = abs(i - mid)
        if ch in "，,、；;…—：:":
            score -= 14
        elif ch in "的了着过吗呢吧啊哦喔么":
            score -= 4
        # Avoid splitting compounds like 只准 / 还可以 / 十分
        if i + 1 < len(u) and u[i : i + 2] in (
            "只准",
            "还可",
            "十分",
            "几乎",
            "已经",
            "没有",
            "不在",
            "一点",
        ):
            score += 20
        # Prefer even-ish length halves
        left, right = i + 1, len(u) - (i + 1)
        if min(left, right) < 3:
            score += 6
        if score < best_score:
            best_score = score
            best = i + 1
    if best is None:
        best = mid
    a, b = u[:best].strip(), u[best:].strip()
    if not a or not b or len(a) < 2 or len(b) < 2:
        return None
    return a, b


def _ensure_caption_density(units: list[str], max_len: int = 14) -> list[str]:
    """Only split *long* phrase lines — never force a target cue count.

    Old logic required ceil(vo_dur/max_unit) cues and shredded good phrases
    into 「是罚你眼睛只 / 准看我。」. Timing rebalance already caps line duration.
    """
    units = list(units)
    # Only split lines that are genuinely long for 9:16 (≥ max_len chars)
    guard = 0
    while guard < 8:
        guard += 1
        long_idx = [i for i, u in enumerate(units) if len(u) >= max_len]
        if not long_idx:
            break
        i = max(long_idx, key=lambda k: len(units[k]))
        parts = _split_one_soft(units[i])
        if not parts:
            break
        a, b = parts
        if len(a) < 4 or len(b) < 4:
            break
        units = units[:i] + [a, b] + units[i + 1 :]
    return units


def unit_timings(
    units: list[str],
    vo_dur: float,
    *,
    min_unit: float = 0.45,
    max_unit: float = 1.55,
    gap: float = 0.02,
) -> list[tuple[str, float, float]]:
    """Full-VO continuous captions, char-weighted, hard-capped per line."""
    if not units:
        return []
    vo_dur = max(0.4, float(vo_dur))
    units = _ensure_caption_density(units)
    n = len(units)
    if n == 1:
        return [(units[0], 0.0, vo_dur)]

    weights = [max(1.0, float(len(u))) for u in units]
    total_w = sum(weights)
    usable = max(0.3, vo_dur - gap * (n - 1))
    durs = [usable * w / total_w for w in weights]
    # Cap and rebalance so no line exceeds max_unit
    for _ in range(8):
        over_idx = [i for i, d in enumerate(durs) if d > max_unit + 1e-6]
        if not over_idx:
            break
        pool = sum(durs[i] - max_unit for i in over_idx)
        for i in over_idx:
            durs[i] = max_unit
        under = [i for i, d in enumerate(durs) if d < max_unit - 1e-6]
        if not under:
            break
        share = pool / len(under)
        for i in under:
            durs[i] = min(max_unit, durs[i] + share)
    durs = [max(min_unit, d) for d in durs]
    span = sum(durs) + gap * (n - 1)
    if span > 0:
        scale = vo_dur / span
        durs = [d * scale for d in durs]

    segs: list[tuple[str, float, float]] = []
    t = 0.0
    for i, (u, dur) in enumerate(zip(units, durs, strict=False)):
        start = t
        end = t + dur
        segs.append((u, start, min(vo_dur, end)))
        t = end + gap
    segs[-1] = (segs[-1][0], segs[-1][1], vo_dur)
    return segs


def tts_to_wav(
    text: str,
    out_mp3: Path,
    voice: str,
    *,
    rate: str = "+0%",
    volume: str = "+0%",
    pitch: str = "+0Hz",
    backend: str | None = None,
    allow_network_fallback: bool = False,
) -> tuple[Path, float, dict[str, Any]]:
    """Synthesize VO via pluggable backend (fish > edge). Returns wav path, duration, meta."""
    out_mp3.parent.mkdir(parents=True, exist_ok=True)
    meta: dict[str, Any] = {"backend": "edge"}
    if tts_synthesize is None:
        raise RenderError("tts_backend.py missing")
    try:
        meta = tts_synthesize(
            text,
            out_mp3,
            backend=backend,
            voice=voice,
            rate=rate,
            volume=volume,
            pitch=pitch,
            allow_network_fallback=allow_network_fallback,
        )
    except Exception as exc:
        raise RenderError(f"TTS failed without cross-provider fallback: {exc}") from exc
    wav = out_mp3.with_suffix(".wav")
    run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(out_mp3),
            "-af",
            "volume=1.25,alimiter=limit=0.95",
            str(wav),
        ]
    )
    return wav, pdur(wav), meta


# Back-compat alias
def tts_edge(
    text: str,
    out_mp3: Path,
    voice: str,
    *,
    rate: str = "+0%",
    volume: str = "+0%",
    pitch: str = "+0Hz",
) -> tuple[Path, float]:
    wav, dur, _ = tts_to_wav(
        text, out_mp3, voice, rate=rate, volume=volume, pitch=pitch, backend="edge"
    )
    return wav, dur


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
) -> np.ndarray:
    """Seductive late-night R&B bed (Rhodes + sub + soft kit). float mono."""
    # Prefer shared implementation from make_sfx_bed when available
    try:
        from make_sfx_bed import rnb_bgm  # type: ignore

        return rnb_bgm(dur, amp=amp, bpm=bpm, seed=seed, shot_starts=shot_starts, events=events)
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

    def _generate_single(g_dur: float, g_mood: str, g_seed: int | None) -> np.ndarray:
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
            return procedural_music_rnb(
                g_dur, amp=amp * 1.05, bpm=76.0, seed=g_seed, shot_starts=shot_starts, events=events
            )

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
        else:  # warm
            notes = [246.9, 293.7, 370.0, 493.9]
            bass = 123.5
            pad = [246.9, 293.7, 370.0]
            counter = [493.9, 440.0, 370.0, 329.6]

        for i, f in enumerate(notes):
            s0, s1 = i * seg_n, (i + 1) * seg_n
            tone = make_tone(f, 0.15, seg_n)
            sig[s0:s1] += tone[: s1 - s0]
        for f in pad:
            sig += make_tone(f, 0.04, n, rel=n / SR)
        sig += make_tone(bass, 0.09, n, rel=n / SR)
        for i, f in enumerate(counter):
            s0, s1 = i * seg_n, (i + 1) * seg_n
            tone = make_tone(f, 0.035, seg_n, rel=0.2)
            sig[s0:s1] += tone[: s1 - s0]
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

        gen_dur = ch_dur
        if i < len(mood_timeline) - 1:
            gen_dur += crossfade_sec

        # Seed mutation: mutate seed per chapter index i
        chapter_seed = base_seed + i
        chapter_sig = _generate_single(gen_dur, str(chapter.get("mood", mood)), chapter_seed)

        i0 = int(st * SR)
        i1 = i0 + len(chapter_sig)
        if i1 > len(final_bed):
            i1 = len(final_bed)
            chapter_sig = chapter_sig[: i1 - i0]

        span = len(chapter_sig)
        if span > 0:
            xfade_samples = min(int(crossfade_sec * SR), span)
            # Equal-Power Crossfade (constant acoustic energy: sin^2 + cos^2 = 1.0)
            if i > 0:
                t_in = np.linspace(0, 1, xfade_samples, endpoint=False)
                chapter_sig[:xfade_samples] *= np.sin(0.5 * np.pi * t_in)

            if i < len(mood_timeline) - 1:
                t_out = np.linspace(0, 1, xfade_samples, endpoint=False)
                chapter_sig[-xfade_samples:] *= np.cos(0.5 * np.pi * t_out)

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
    import re

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


def build_native_track(
    shots: list[dict[str, Any]],
    *,
    title_duration: float,
    end_duration: float,
    work: Path,
    audio_dir: Path,
    transition_sec: float = 0.0,
    join_intents: list[str] | None = None,
) -> Path:
    """Align generated clip audio to the edited timeline, filling missing stems with silence.

    When transition_sec > 0, joins use the same acrossfade overlaps as VO/video so native
    stems stay on the xfade clock (not a hard-concat that drifts ahead of picture).
    """
    segments: list[tuple[Path | None, float]] = [(None, title_duration)]
    segments.extend((item.get("native_audio"), float(item["target"])) for item in shots)
    segments.append((None, end_duration))
    segment_durs = [float(duration) for _, duration in segments]
    parts: list[Path] = []
    for index, (source, duration) in enumerate(segments):
        part = work / f"native_part_{index:02d}.wav"
        if source is not None:
            run(
                [
                    "ffmpeg",
                    "-y",
                    "-stream_loop",
                    "-1",
                    "-i",
                    str(source),
                    "-t",
                    f"{duration:.3f}",
                    "-af",
                    f"atrim=0:{duration:.3f},asetpts=PTS-STARTPTS",
                    "-ar",
                    str(SR),
                    "-ac",
                    "2",
                    "-c:a",
                    "pcm_s16le",
                    str(part),
                ]
            )
        else:
            run(
                [
                    "ffmpeg",
                    "-y",
                    "-f",
                    "lavfi",
                    "-i",
                    f"anullsrc=r={SR}:cl=stereo",
                    "-t",
                    f"{duration:.3f}",
                    "-c:a",
                    "pcm_s16le",
                    str(part),
                ]
            )
        parts.append(part)
    try:
        output = safe_output_path(
            audio_dir, "native_track.wav", suffixes={".wav"}, field="native audio track"
        )
    except SecurityPolicyError as exc:
        raise RenderError(str(exc)) from exc
    try:
        t_sec = normalize_transition_sec(transition_sec)
    except PolicyError as exc:
        raise RenderError(str(exc)) from exc
    concat_audio_segments(
        parts,
        output,
        transition_sec=t_sec,
        segment_durs=segment_durs,
        join_intents=join_intents,
    )
    return output


def build_vocal_color_track(
    shot_audio: list[dict[str, Any]],
    *,
    shot_start_map: dict[str, float],
    total_duration: float,
    work: Path,
    audio_dir: Path,
) -> Path | None:
    """Overlay per-shot 娇喘/语助词 stems onto the film timeline (independent of nar).

    Returns path to vocal_color_track.wav, or None when no color stems.
    """
    placements: list[tuple[Path, float, float]] = []  # wav, delay_sec, gain
    for item in shot_audio:
        c_wav = item.get("color_wav")
        if not c_wav:
            continue
        try:
            c_path = Path(c_wav)
        except TypeError:
            continue
        if not c_path.is_file():
            continue
        sid = str(item.get("id") or "")
        start = float(shot_start_map.get(sid, 0.0))
        plate = float(item.get("target") or 0.0)
        c_dur = float(item.get("color_dur") or 0.0)
        off = item.get("color_offset_sec")
        if compute_color_offset_sec is not None:
            off_sec = compute_color_offset_sec(
                offset_sec=float(off) if off is not None else -1.0,
                plate_sec=plate,
                color_dur=c_dur if c_dur > 0 else 0.4,
                vo_dur=float(item.get("raw_vo_dur") or item.get("vo_dur") or 0.0),
            )
        else:
            off_sec = max(0.0, float(off) if off is not None and float(off) >= 0 else plate * 0.55)
        delay = start + off_sec
        gain = float(item.get("color_gain") or DEFAULT_VOCAL_COLOR_GAIN)
        if gain <= 0:
            continue
        placements.append((c_path, delay, gain))

    try:
        output = safe_output_path(
            audio_dir, "vocal_color_track.wav", suffixes={".wav"}, field="vocal color track"
        )
    except SecurityPolicyError as exc:
        raise RenderError(str(exc)) from exc

    if not placements:
        # Default path: no color stems → skip track (mix stays nar+BGM+native).
        return None

    # Silence base + delayed stems amixed
    base = work / "color_base_silence.wav"
    run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"anullsrc=r={SR}:cl=stereo",
            "-t",
            f"{max(0.05, float(total_duration)):.3f}",
            "-c:a",
            "pcm_s16le",
            str(base),
        ]
    )
    delayed_parts: list[Path] = [base]
    for idx, (src, delay, gain) in enumerate(placements):
        part = work / f"color_place_{idx:02d}.wav"
        delay_ms = max(0, int(round(delay * 1000.0)))
        # adelay + pad to full timeline length
        run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(src),
                "-af",
                (
                    f"aformat=sample_fmts=fltp:sample_rates={SR}:channel_layouts=stereo,"
                    f"volume={gain:.3f},"
                    f"adelay={delay_ms}|{delay_ms},"
                    f"apad=whole_dur={max(0.05, float(total_duration)):.3f}"
                ),
                "-t",
                f"{max(0.05, float(total_duration)):.3f}",
                "-ar",
                str(SR),
                "-ac",
                "2",
                "-c:a",
                "pcm_s16le",
                str(part),
            ]
        )
        delayed_parts.append(part)

    # amix all
    n_in = len(delayed_parts)
    inputs: list[str] = []
    for p in delayed_parts:
        inputs.extend(["-i", str(p)])
    fc = (
        "".join(f"[{i}:a]" for i in range(n_in)) + f"amix=inputs={n_in}:duration=first:normalize=0,"
        f"aformat=sample_fmts=fltp:sample_rates={SR}:channel_layouts=stereo,"
        f"alimiter=limit=0.92[aout]"
    )
    run(
        [
            "ffmpeg",
            "-y",
            *inputs,
            "-filter_complex",
            fc,
            "-map",
            "[aout]",
            "-ar",
            str(SR),
            "-ac",
            "2",
            "-c:a",
            "pcm_s16le",
            str(output),
        ]
    )
    return output


def _wrap_title_lines(text: str, max_chars: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for char in text:
        current += char
        if char in "，。！？… " or len(current) >= max_chars:
            lines.append(current.strip())
            current = ""
    if current.strip():
        lines.append(current.strip())
    return lines


def sub_png(
    text: str,
    path: Path,
    *,
    width: int,
    height: int,
    font_path: str,
    title: bool = False,
    dodge: bool = False,
    italic: bool = False,
) -> None:
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    if title:
        font = ImageFont.truetype(font_path, max(42, width // 18))
        lines = _wrap_title_lines(text, 10)
        lh = font.size + 18
        total_h = len(lines) * lh
        y0 = (height - total_h) // 2
        for i, line in enumerate(lines):
            bbox = draw.textbbox((0, 0), line, font=font)
            tw = bbox[2] - bbox[0]
            x = (width - tw) // 2
            draw.text(
                (x, y0 + i * lh),
                line,
                font=font,
                fill=(255, 236, 242, 255),
                stroke_width=2,
                stroke_fill=(40, 10, 24, 255),
            )
    else:
        try:
            from subtitle_typesetter import break_text_semantically

            lines = break_text_semantically(text, max_chars=18)
        except Exception:
            lines = [text]

        font = ImageFont.truetype(font_path, max(30, width // 21))
        lh = font.size + 10
        total_th = len(lines) * lh
        bar_h = total_th + max(40, height // 20)

        text_img = Image.new("RGBA", (width, bar_h + 20), (0, 0, 0, 0))
        text_draw = ImageDraw.Draw(text_img)

        y0 = (bar_h - total_th) // 2

        for i, line in enumerate(lines):
            bbox = text_draw.textbbox((0, 0), line, font=font)
            tw = bbox[2] - bbox[0]
            x = (width - tw) // 2
            y = y0 + i * lh

            # soft drop shadow
            shadow_offset = 3
            text_draw.text(
                (x + shadow_offset, y + shadow_offset),
                line,
                font=font,
                fill=(0, 0, 0, 180),
                stroke_width=3,
                stroke_fill=(0, 0, 0, 180),
            )
            # main text with stroke
            text_draw.text(
                (x, y),
                line,
                font=font,
                fill=(255, 250, 252, 255),
                stroke_width=2,
                stroke_fill=(0, 0, 0, 255),
            )

        if italic:
            text_img = text_img.transform(
                (width, bar_h + 20),
                Image.AFFINE,
                (1, -0.25, 0.25 * (bar_h / 2), 0, 1, 0),
                resample=Image.BICUBIC,
            )

        if dodge:
            for dy in range(bar_h):
                a = int(120 + 70 * ((bar_h - dy) / max(1, bar_h - 1)))
                draw.line([(0, dy), (width, dy)], fill=(0, 0, 0, a))
            img.alpha_composite(text_img, (0, 0))
        else:
            for dy in range(bar_h):
                a = int(120 + 70 * (dy / max(1, bar_h - 1)))
                draw.line(
                    [(0, height - bar_h + dy), (width, height - bar_h + dy)], fill=(0, 0, 0, a)
                )
            img.alpha_composite(text_img, (0, height - bar_h))

    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)


def mkcard_video(
    text: str, out: Path, *, width: int, height: int, duration: float, fps: int, font_path: str
) -> None:
    """Title/end card: dark wine gradient + soft highlight (色气 short-film feel).

    Empty ``text`` → **blank pad** (same gradient, no glyphs). Used when designed
    post (HyperFrames/Remotion) owns title/end lettering so FFmpeg does not
    double-burn under the designed card.
    """
    work = out.parent
    png = work / f"{out.stem}_card.png"
    img = Image.new("RGB", (width, height), (12, 6, 14))
    draw = ImageDraw.Draw(img)
    # vertical gradient (deep plum → near black)
    for y in range(height):
        t = y / max(1, height - 1)
        r = int(18 + 22 * (1 - t))
        g = int(6 + 4 * (1 - t))
        b = int(22 + 18 * (1 - t))
        draw.line([(0, y), (width, y)], fill=(r, g, b))
    # soft vignette bars
    draw.rectangle([0, 0, width, height // 8], fill=(0, 0, 0))
    draw.rectangle([0, height - height // 8, width, height], fill=(0, 0, 0))
    label = (text or "").strip()
    if label:
        font = ImageFont.truetype(font_path, max(40, width // 16))
        # CJK short titles: keep one line (max_chars high enough to avoid 戏服玩心|夜)
        lines = _wrap_title_lines(label, max(16, len(label)))
        lh = font.size + 18
        y0 = (height - len(lines) * lh) // 2
        for i, line in enumerate(lines):
            bbox = draw.textbbox((0, 0), line, font=font)
            tw = bbox[2] - bbox[0]
            x = (width - tw) // 2
            # soft pink-white for 色气 title
            draw.text(
                (x, y0 + i * lh),
                line,
                font=font,
                fill=(255, 236, 242),
                stroke_width=2,
                stroke_fill=(40, 10, 24),
            )
    img.save(png)
    run(
        [
            "ffmpeg",
            "-y",
            "-loop",
            "1",
            "-r",
            str(fps),
            "-i",
            str(png),
            "-t",
            f"{duration:.3f}",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-r",
            str(fps),
            str(out),
        ]
    )


def flatten_shots(spec: dict[str, Any], film_root: Path | None = None) -> list[dict[str, Any]]:
    try:
        return validate_film_spec(spec, assign_missing_ids=False, film_root=film_root)
    except FilmSpecError as exc:
        raise RenderError(str(exc)) from exc


def _shot_speaker_key(shot: dict[str, Any]) -> str:
    raw = shot.get("speaker") or shot.get("role") or ""
    return str(raw).strip().lower()


def is_character_speech_shot(shot: dict[str, Any]) -> bool:
    """True when this plate should use character-dialogue TTS (not pure storyteller)."""
    sp = _shot_speaker_key(shot)
    if sp and sp not in _NARRATOR_SPEAKERS:
        return True
    for key in ("dialogue", "dialogue_ja", "nar_ja", "spoken_ja"):
        val = shot.get(key)
        if isinstance(val, str) and val.strip():
            return True
    explicit = str(shot.get("vo_voice") or shot.get("voice") or "")
    if explicit.startswith("ja-JP-") or explicit.startswith("ja-"):
        return True
    return False


def narration_for_shot(shot: dict[str, Any]) -> str:
    """Chinese / default caption+legacy text (not necessarily what TTS speaks)."""
    for key in ("nar", "narration", "nar_zh", "dialogue", "vo", "caption"):
        val = shot.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    for key in ("purpose", "title"):
        val = shot.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def caption_text_for_shot(shot: dict[str, Any], *, caption_lang: str = "zh") -> str:
    """On-screen subtitle text. Default Chinese even when TTS is Japanese."""
    lang = (caption_lang or "zh").strip().lower()
    if lang in {"ja", "jp", "japanese"}:
        for key in ("nar_ja", "dialogue_ja", "spoken_ja", "nar", "narration"):
            val = shot.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
    # zh / default: never let Japanese be the only caption source when Chinese exists
    for key in ("nar", "narration", "nar_zh", "caption", "dialogue"):
        val = shot.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    for key in ("nar_ja", "dialogue_ja"):
        val = shot.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return narration_for_shot(shot)


def spoken_text_for_shot(
    shot: dict[str, Any],
    *,
    dialogue_spoken_lang: str = "ja",
    narration_spoken_lang: str = "zh",
    vo_mode: str = "storyteller",
) -> str:
    """Text fed to TTS. Character lines prefer Japanese when policy is ja."""
    dlang = (dialogue_spoken_lang or "ja").strip().lower()
    nlang = (narration_spoken_lang or "zh").strip().lower()
    character = is_character_speech_shot(shot)
    if character and dlang in {"ja", "jp", "japanese"}:
        for key in ("nar_ja", "dialogue_ja", "spoken_ja", "dialogue"):
            val = shot.get(key)
            if isinstance(val, str) and val.strip():
                # Prefer Japanese scripts; skip pure CJK Chinese if ja field missing
                text = val.strip()
                if key in {"nar_ja", "dialogue_ja", "spoken_ja"}:
                    return text
                # dialogue field may be Chinese — only use if no ja and looks JP-ish
                if any("\u3040" <= ch <= "\u30ff" or "\u31f0" <= ch <= "\u31ff" for ch in text):
                    return text
        # Soft fallback: Chinese dialogue still spoken (agent should fill nar_ja)
        for key in ("dialogue", "nar", "narration"):
            val = shot.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
    if nlang in {"ja", "jp", "japanese"} and not character:
        for key in ("nar_ja", "nar", "narration"):
            val = shot.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
    return narration_for_shot(shot)


def voice_for_shot(
    shot: dict[str, Any],
    *,
    default_voice: str,
    cast_voices: dict[str, str] | None,
    vo_mode: str,
    dialogue_spoken_lang: str = "ja",
) -> str:
    """Resolve one stable voice id for this shot — 一角一声.

    Priority: shot.vo_voice → cast_voices[speaker|cast] → JA character defaults → default_voice
    Storyteller mode ignores per-shot cast unless shot.speaker is set.
    """
    cast_voices = cast_voices or {}
    explicit = shot.get("vo_voice") or shot.get("voice")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    speaker = shot.get("speaker") or shot.get("role")
    if isinstance(speaker, str) and speaker.strip() and speaker.strip() in cast_voices:
        return cast_voices[speaker.strip()]
    # map first cast tag if present (character mode)
    casts = (
        shot.get("dsl", {}).get("cast") if isinstance(shot.get("dsl"), dict) else shot.get("cast")
    )
    if isinstance(casts, list) and casts:
        c0 = str(casts[0]).strip()
        if c0 in cast_voices:
            return cast_voices[c0]
    sp = _shot_speaker_key(shot)
    dlang = (dialogue_spoken_lang or "ja").strip().lower()
    if is_character_speech_shot(shot) and dlang in {"ja", "jp", "japanese"}:
        if sp in cast_voices:
            return cast_voices[sp]
        if sp in _PARTNER_SPEAKERS or any(k in cast_voices for k in ("partner", "male_hero")):
            for k in ("partner", "male_hero", "hero"):
                if k in cast_voices:
                    return cast_voices[k]
            if sp in _PARTNER_SPEAKERS:
                return PARTNER_JA_VOICE
        if sp in _HEROINE_SPEAKERS or "heroine" in cast_voices:
            if "heroine" in cast_voices:
                return cast_voices["heroine"]
            return HEROINE_JA_VOICE
        # character speech without clear gender → heroine JA default
        return cast_voices.get("heroine") or HEROINE_JA_VOICE
    if vo_mode == "storyteller" and "storyteller" in cast_voices:
        return cast_voices["storyteller"]
    if "storyteller" in cast_voices and not is_character_speech_shot(shot):
        return cast_voices["storyteller"]
    return default_voice


def stretch_clip(
    src: Path,
    dest: Path,
    *,
    target: float,
    width: int,
    height: int,
    fps: int,
    dramatic_function: str | None = None,
    in_point_sec: float | None = None,
    out_point_sec: float | None = None,
) -> dict[str, Any]:
    """Fit silent I2V clip to VO length using plan_stretch.

    hook/action never stream_loop (forbid_loop). Other beats may loop when VO >> plate.
    Optional in/out points trim the plate before fit (join-handle / mid-action cut).
    Returns the stretch plan dict for logging/tests.
    """
    full_dur = pdur(src)
    if full_dur <= 0:
        raise RenderError(f"Bad source duration: {src}")
    # Join handle: use only [in, out) so match-cut lands mid-motion
    t0 = float(in_point_sec) if in_point_sec is not None and in_point_sec > 0 else 0.0
    t1 = float(out_point_sec) if out_point_sec is not None and out_point_sec > 0 else full_dur
    t0 = max(0.0, min(t0, full_dur - 0.05))
    t1 = max(t0 + 0.05, min(t1, full_dur))
    src_dur = t1 - t0
    try:
        plan = plan_stretch(src_dur, target, dramatic_function=dramatic_function)
    except PolicyError as exc:
        raise RenderError(str(exc)) from exc
    # P0 · 2026-07-23: shortform clamp may shrink target (anti stream_loop double-play)
    if plan.get("target_clamped") is not None:
        with contextlib.suppress(TypeError, ValueError):
            target = float(plan["target_clamped"])
    plan["in_point_sec"] = t0
    plan["out_point_sec"] = t1
    plan["source_full_dur"] = full_dur
    plan["effective_target"] = target

    base = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,"
        f"fps={fps},format=yuv420p"
    )
    factor = float(plan["factor"])
    ss_args: list[str] = []
    if t0 > 1e-3:
        ss_args = ["-ss", f"{t0:.3f}"]

    # Trim source to [t0, t1) first via -ss/-t on input, then fit to target
    input_t_args: list[str] = []
    if t0 > 1e-3 or (out_point_sec is not None):
        input_t_args = ["-t", f"{src_dur:.3f}"]

    if plan["mode"] == "loop":
        vf = f"{base},setpts={factor:.4f}*PTS"
        run(
            [
                "ffmpeg",
                "-y",
                *ss_args,
                "-stream_loop",
                str(int(plan["loops"])),
                "-i",
                str(src),
                *input_t_args,
                "-vf",
                vf,
                "-an",
                "-t",
                f"{target:.3f}",
                "-r",
                str(fps),
                "-c:v",
                "libx264",
                "-preset",
                "fast",
                "-crf",
                "20",
                str(dest),
            ]
        )
        return plan

    vf = f"{base},setpts={factor:.4f}*PTS"
    freeze = float(plan.get("freeze_sec") or 0.0)
    if freeze > 0.05:
        vf = f"{vf},tpad=stop_mode=clone:stop_duration={freeze:.3f}"
    run(
        [
            "ffmpeg",
            "-y",
            *ss_args,
            "-i",
            str(src),
            *input_t_args,
            "-vf",
            vf,
            "-an",
            "-t",
            f"{target:.3f}",
            "-r",
            str(fps),
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "20",
            str(dest),
        ]
    )
    return plan


def concat_videos(
    parts: list[Path],
    out: Path,
    *,
    transition_sec: float = DEFAULT_TRANSITION_SEC,
    fps: int = 30,
    join_intents: list[str] | None = None,
    transition_style: str = "fade",
    join_styles: list[str] | None = None,
    join_use_ts: list[float] | None = None,
) -> dict[str, Any]:
    """Concatenate clips with optional per-join hard/soft/hold transitions."""
    if not parts:
        raise RenderError("concat_videos: no parts")
    try:
        t_sec = normalize_transition_sec(transition_sec)
    except PolicyError as exc:
        raise RenderError(str(exc)) from exc

    durs = [pdur(p) for p in parts]
    style = (transition_style or "fade").strip().lower() or "fade"
    try:
        plan = build_xfade_filter_graph(
            durs,
            transition_sec=t_sec,
            transition=style,
            join_intents=join_intents,
            join_styles=join_styles,
            join_use_ts=join_use_ts,
        )
    except PolicyError as exc:
        raise RenderError(str(exc)) from exc

    if not plan["enabled"]:
        lst = out.parent / "concat_final.txt"
        atomic_write_text(lst, "".join(f"file '{p.resolve()}'\n" for p in parts))
        run(
            [
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
                "-r",
                str(fps),
                str(out),
            ]
        )
        return {**plan, "method": plan.get("method") or "hard_concat"}

    cmd: list[str] = ["ffmpeg", "-y"]
    for p in parts:
        cmd += ["-i", str(p)]
    cmd += [
        "-filter_complex",
        plan["filter_complex"],
        "-map",
        f"[{plan['output_label']}]",
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        "-r",
        str(fps),
        "-an",
        str(out),
    ]
    run(cmd)
    return {**plan, "method": plan.get("method") or "xfade"}


def concat_audio_segments(
    parts: list[Path],
    out: Path,
    *,
    transition_sec: float = DEFAULT_TRANSITION_SEC,
    segment_durs: list[float] | None = None,
    join_intents: list[str] | None = None,
) -> dict[str, Any]:
    """Join VO (or BGM) stems with acrossfade / hard joins matching video."""
    if not parts:
        raise RenderError("concat_audio_segments: no parts")
    try:
        t_sec = normalize_transition_sec(transition_sec)
    except PolicyError as exc:
        raise RenderError(str(exc)) from exc

    durs = segment_durs
    if durs is None:
        durs = [pdur(p) for p in parts]
    if len(durs) != len(parts):
        raise RenderError("concat_audio_segments: segment_durs length mismatch")

    try:
        plan = build_acrossfade_filter_graph(
            len(parts),
            transition_sec=t_sec,
            segment_durs=durs,
            join_intents=join_intents,
        )
    except PolicyError as exc:
        raise RenderError(str(exc)) from exc
    if not plan["enabled"]:
        lst = out.parent / f"{out.stem}_alist.txt"
        atomic_write_text(lst, "".join(f"file '{p.resolve()}'\n" for p in parts))
        run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(lst),
                "-c:a",
                "pcm_s16le",
                str(out),
            ]
        )
        return {**plan, "method": "hard_concat", "segment_durs": durs}

    cmd: list[str] = ["ffmpeg", "-y"]
    for p in parts:
        cmd += ["-i", str(p)]
    cmd += [
        "-filter_complex",
        plan["filter_complex"],
        "-map",
        f"[{plan['output_label']}]",
        "-c:a",
        "pcm_s16le",
        str(out),
    ]
    run(cmd)
    return {**plan, "method": "acrossfade", "segment_durs": durs}


def build_subtitle_cues_for_shots(
    shot_audio: list[dict[str, Any]],
    *,
    title_duration: float,
    end_duration: float,
    transition_sec: float,
    sub_lead: float = 0.08,
    sub_min: float = 0.48,
    sub_max: float = 1.75,
    story_join_intents: list[str] | None = None,
    default_intent: str = "soft",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Place captions on the xfade timeline (same starts as video/native/VO joins).

    Returns (cues, film_timeline). Using hard-cut t0+=target would lag ~transition_sec
    per join once xfade shortens the picture clock.
    """
    film_tl = film_segment_timeline(
        title_duration=title_duration,
        shot_targets=[float(item["target"]) for item in shot_audio],
        end_duration=end_duration,
        transition_sec=transition_sec,
        story_join_intents=story_join_intents,
        default_intent=default_intent,
    )
    cues: list[dict[str, Any]] = []
    shot_starts = list(film_tl["shot_starts"])
    for i, item in enumerate(shot_audio):
        t0 = float(shot_starts[i])
        # CRITICAL: use raw speech length, NOT padded plate vo_dur.
        # After pad_natural, item["vo_dur"] == plate (silence tail); spreading
        # phrases over that makes late cards appear with no VO (user: 字幕對不上口白).
        speech_dur = float(item.get("raw_vo_dur") or item.get("vo_dur") or item["target"] or 0.0)
        plate = float(item.get("target") or speech_dur or 0.0)
        # never schedule captions into the pad tail (keep ≥0.15s headroom if pad)
        if plate > speech_dur + 0.2:
            speech_dur = min(speech_dur, plate - 0.05)
        speech_dur = max(0.4, speech_dur)
        units = list(item.get("units") or [])
        segs = unit_timings(
            units,
            speech_dur,
            min_unit=sub_min,
            max_unit=sub_max,
            gap=0.03,
        )
        speech_end = t0 + speech_dur
        shot_end = t0 + plate - 0.02
        hard_end = min(speech_end, shot_end)
        # Determine italic from voice_type or intent
        is_monologue = False
        nar_item = item.get("narration") or {}
        if isinstance(nar_item, dict) and nar_item.get("voice_type") == "internal_monologue":
            is_monologue = True

        for u, bs, be in segs:
            sb = max(0.0, t0 + bs - sub_lead)
            eb = t0 + be
            if eb - sb < sub_min:
                eb = sb + sub_min
            if eb > hard_end:
                eb = hard_end
            if eb <= sb:
                eb = min(hard_end, sb + 0.4)
            cues.append(
                {"start": sb, "end": eb, "text": u, "shot_index": i, "is_monologue": is_monologue}
            )
    return cues, film_tl


def write_srt(path: Path, cues: list[dict[str, Any]]) -> None:
    """Write an SRT sidecar file. Delegates to the shared subtitle_srt module.

    v1.23: extracted to subtitle_srt.write_srt_file so all post-engines
    (ffmpeg / hyperframes / remotion) share one validated SRT generator.
    Kept as a thin wrapper for backward compatibility with internal callers.
    """
    from subtitle_srt import write_srt_file

    write_srt_file(path, cues)


def render_final(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root).expanduser().resolve()
    try:
        out_dir = safe_workspace_directory(root, "out", field="film output directory")
        final_path = safe_output_path(
            out_dir,
            args.out_name or "film_final.mp4",
            suffixes={".mp4"},
            field="final output name",
        )
    except SecurityPolicyError as exc:
        raise RenderError(str(exc)) from exc
    if not root.is_dir():
        raise RenderError(f"Film root missing: {root}")
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise RenderError("ffmpeg/ffprobe required")

    if tts_synthesize is None:
        raise RenderError("tts_backend.py missing next to render_final.py")

    manifest = read_json(root / "manifest.json")
    spec = read_json(root / "film-spec.json")
    audio_contract = validate_audio_tracks_contract(spec)
    for warning in audio_contract.get("warnings") or []:
        log(f"audio contract warning: {warning}")
    # Hard gate: long VO on short plates → stream_loop (boring). Split nars first.
    from production_gates import ProductionGateError, assert_no_loop_risk

    try:
        assert_no_loop_risk(root, force=bool(getattr(args, "allow_loop_risk", False)))
    except ProductionGateError as exc:
        raise RenderError(str(exc)) from exc
    timeline = read_json(root / "timeline.json") if (root / "timeline.json").is_file() else {}
    width = int(args.width or timeline.get("width") or manifest.get("width") or 720)
    height = int(args.height or timeline.get("height") or manifest.get("height") or 1280)
    fps = int(args.fps or timeline.get("fps") or 30)
    # Film-spec may override VO strategy
    vo_mode = str(spec.get("vo_mode") or "storyteller").lower()
    # 默认中文女声（晓晓 edge 兜底）；Fish 时 voice 可填 FISH voice id
    voice = (
        args.voice
        or spec.get("vo_voice")
        or (STORYTELLER_VOICE if vo_mode in ("storyteller", "hybrid") else DEFAULT_VOICE)
    )
    # 一角一声：film-spec.cast_voices = {"storyteller": "zh-CN-XiaoxiaoNeural", "heroine": "..."}
    cast_voices_raw = spec.get("cast_voices") or {}
    cast_voices: dict[str, str] = {}
    if isinstance(cast_voices_raw, dict):
        for k, v in cast_voices_raw.items():
            if isinstance(k, str) and isinstance(v, str) and k.strip() and v.strip():
                cast_voices[k.strip()] = v.strip()
    # P0 · 2026-07-23: default JA character voices when dialogue_spoken_lang=ja
    _dlg_lang = (
        str(
            spec.get("dialogue_spoken_lang")
            or (spec.get("voice_policy") or {}).get("dialogue_spoken_lang")
            or "ja"
        )
        .strip()
        .lower()
    )
    if _dlg_lang in {"ja", "jp", "japanese"}:
        cast_voices.setdefault("heroine", HEROINE_JA_VOICE)
        cast_voices.setdefault("partner", PARTNER_JA_VOICE)
        cast_voices.setdefault("male_hero", PARTNER_JA_VOICE)
    cast_voices.setdefault("storyteller", STORYTELLER_VOICE)
    vo_rate = str(getattr(args, "vo_rate", None) or spec.get("vo_rate") or DEFAULT_VO_RATE)
    vo_pitch = str(getattr(args, "vo_pitch", None) or spec.get("vo_pitch") or DEFAULT_VO_PITCH)
    vo_tts_vol = str(getattr(args, "vo_tts_volume", None) or spec.get("vo_tts_volume") or "+0%")
    tts_backend = (
        getattr(args, "tts_backend", None)
        or spec.get("tts_backend")
        or os.environ.get("AIFILM_TTS_BACKEND")
        or "auto"
    )
    tts_allow_network_fallback = bool(spec.get("tts_allow_network_fallback", False))
    raw_native_volume = getattr(args, "native_audio_volume", None)
    if raw_native_volume is None:
        raw_native_volume = spec.get("native_audio_volume", 0.16)
    native_audio_volume = float(raw_native_volume)
    if native_audio_volume < 0 or native_audio_volume > 1:
        raise RenderError("native_audio_volume must be between 0 and 1")
    raw_gain = getattr(args, "vo_gain", None)
    if raw_gain is None:
        raw_gain = spec.get("vo_gain")
    vo_gain = float(raw_gain if raw_gain is not None else DEFAULT_VO_GAIN)
    # Multi-track voice policy (nar vs 娇喘语助 vs native)
    voice_policy: dict[str, Any] = {}
    if resolve_voice_tracks is not None:
        try:
            voice_policy = resolve_voice_tracks(spec)
        except Exception:
            voice_policy = {}
    if voice_policy.get("nar_gain") is not None:
        with contextlib.suppress(TypeError, ValueError):
            vo_gain = float(voice_policy["nar_gain"])
    if voice_policy.get("native_audio_volume") is not None:
        with contextlib.suppress(TypeError, ValueError):
            native_audio_volume = float(voice_policy["native_audio_volume"])
    raw_color_gain = getattr(args, "vocal_color_gain", None)
    if raw_color_gain is None:
        raw_color_gain = voice_policy.get("vocal_color_gain")
    if raw_color_gain is None:
        raw_color_gain = spec.get("vocal_color_gain")
    try:
        film_vocal_color_gain = float(
            raw_color_gain if raw_color_gain is not None else DEFAULT_VOCAL_COLOR_GAIN
        )
    except (TypeError, ValueError):
        film_vocal_color_gain = DEFAULT_VOCAL_COLOR_GAIN
    film_vocal_color_gain = max(0.0, min(1.5, film_vocal_color_gain))
    # 色气 / storyteller → seductive R&B by default；音乐必须远低于旁白
    mood = args.music_mood or ("rnb" if vo_mode in ("storyteller", "hybrid") else "playful")
    lipsync_mode = (getattr(args, "lipsync", None) or "off").lower()
    # Storyteller: never lipsync unless user forced --lipsync require
    if vo_mode == "storyteller" and lipsync_mode not in (
        "require",
        "musetalk",
        "wav2lip",
        "external",
    ):
        if lipsync_mode != "off":
            log("storyteller mode → force lipsync off")
        lipsync_mode = "off"
    tts_info = tts_probe() if tts_probe else {}
    log(
        f"vo_mode={vo_mode} tts={tts_backend}->{tts_info.get('active')} voice={voice} "
        f"rate={vo_rate} pitch={vo_pitch} vo_gain={vo_gain} music_vol={args.music_volume} "
        f"mood={mood} lipsync={lipsync_mode}"
    )
    font_path = resolve_font()

    shots = flatten_shots(spec, film_root=root)
    clips_map = manifest.get("clips") or {}
    try:
        clips_dir = safe_workspace_directory(root, "clips", field="film clips directory")
        audio_dir = safe_workspace_directory(root, "audio", field="film audio directory")
        native_dir = safe_workspace_directory(audio_dir, "native", field="native audio directory")
        keyframes_dir = safe_workspace_directory(
            root, "keyframes", field="film keyframes directory"
        )
        work = safe_workspace_directory(out_dir, "_final_work", field="final work directory")
        for directory, field in (
            (out_dir, "film output directory"),
            (audio_dir, "film audio directory"),
            (clips_dir, "film clips directory"),
            (keyframes_dir, "film keyframes directory"),
            (native_dir, "native audio directory"),
        ):
            reject_symlinks(directory, field=field)
    except SecurityPolicyError as exc:
        raise RenderError(str(exc)) from exc
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    audio_dir.mkdir(exist_ok=True)
    overlays_dir = work / "overlays"
    overlays_dir.mkdir()

    # 1) Per-shot TTS
    shot_audio: list[dict[str, Any]] = []
    for i, shot in enumerate(shots):
        sid = shot["id"]
        rec = clips_map.get(sid)
        if not approved_clip_record(rec):
            raise RenderError(
                f"Clip {sid} lacks endpoint, identity, motion, review-note, or decode QA evidence"
            )
        try:
            clip_path = safe_existing_file(clips_dir, rec["path"], field=f"clip path for {sid}")
        except (KeyError, SecurityPolicyError) as exc:
            raise RenderError(str(exc)) from exc
        native_audio = None
        native_record = rec.get("native_audio")
        if isinstance(native_record, dict):
            try:
                native_audio = safe_existing_file(
                    native_dir, native_record["path"], field=f"native audio path for {sid}"
                )
            except (KeyError, SecurityPolicyError) as exc:
                raise RenderError(str(exc)) from exc
            if native_record.get("sha256") != sha256(native_audio):
                raise RenderError(f"Native audio fingerprint changed for {sid}")
        dialogue_spoken_lang = str(
            spec.get("dialogue_spoken_lang")
            or (spec.get("voice_policy") or {}).get("dialogue_spoken_lang")
            or "ja"
        )
        narration_spoken_lang = str(
            spec.get("narration_spoken_lang")
            or (spec.get("voice_policy") or {}).get("narration_spoken_lang")
            or "zh"
        )
        caption_lang = str(
            spec.get("caption_lang") or (spec.get("voice_policy") or {}).get("caption_lang") or "zh"
        )
        text = spoken_text_for_shot(
            shot,
            dialogue_spoken_lang=dialogue_spoken_lang,
            narration_spoken_lang=narration_spoken_lang,
            vo_mode=vo_mode,
        )
        caption_text = caption_text_for_shot(shot, caption_lang=caption_lang) or text
        if not text:
            raise RenderError(
                f"Shot {sid} has no spoken text for VO "
                f"(need nar/nar_ja/dialogue; character lines prefer nar_ja when "
                f"dialogue_spoken_lang=ja)"
            )
        max_chars = int(
            getattr(args, "sub_max_chars", DEFAULT_SUB_MAX_CHARS) or DEFAULT_SUB_MAX_CHARS
        )
        # Subtitles use caption language (default zh); TTS may be Japanese
        units = split_units(caption_text, max_len=max_chars)
        try:
            mp3 = safe_output_path(
                audio_dir, f"{sid}_vo.mp3", suffixes={".mp3"}, field=f"VO output for {sid}"
            )
            safe_output_path(
                audio_dir, f"{sid}_vo.wav", suffixes={".wav"}, field=f"VO WAV output for {sid}"
            )
        except SecurityPolicyError as exc:
            raise RenderError(str(exc)) from exc
        log(f"TTS {sid}: {text[:40]}...")
        shot_voice = voice_for_shot(
            shot,
            default_voice=voice,
            cast_voices=cast_voices,
            vo_mode=vo_mode,
            dialogue_spoken_lang=dialogue_spoken_lang,
        )
        wav, dur, tts_meta = tts_to_wav(
            text,
            mp3,
            shot_voice,
            rate=vo_rate,
            volume=vo_tts_vol,
            pitch=vo_pitch,
            backend=None if tts_backend == "auto" else str(tts_backend),
            allow_network_fallback=tts_allow_network_fallback,
        )
        log(
            f"  tts backend={tts_meta.get('backend')} voice={tts_meta.get('voice') or shot_voice} "
            f"dur={dur:.2f}s"
        )
        # Independent 娇喘/语助词 stem (not mixed into nar text)
        color_wav: Path | None = None
        color_dur = 0.0
        color_meta: dict[str, Any] | None = None
        color_payload: dict[str, Any] = {}
        if resolve_shot_vocal_color is not None and voice_policy.get("enabled", False):
            try:
                color_payload = resolve_shot_vocal_color(shot, policy=voice_policy, seed=i * 17)
            except Exception:
                color_payload = {}
        color_text = str(color_payload.get("text") or "").strip()
        color_gain = float(color_payload.get("gain") or film_vocal_color_gain or 0.0)
        if color_text and color_gain > 0 and film_vocal_color_gain > 0:
            try:
                c_mp3 = safe_output_path(
                    audio_dir,
                    f"{sid}_color.mp3",
                    suffixes={".mp3"},
                    field=f"vocal color output for {sid}",
                )
                safe_output_path(
                    audio_dir,
                    f"{sid}_color.wav",
                    suffixes={".wav"},
                    field=f"vocal color wav for {sid}",
                )
                log(f"  vocal_color TTS {sid}: {color_text[:24]}...")
                color_wav, color_dur, color_meta = tts_to_wav(
                    color_text,
                    c_mp3,
                    shot_voice,
                    rate=str(color_payload.get("rate") or "+0%"),
                    volume=vo_tts_vol,
                    pitch=str(color_payload.get("pitch") or "+2Hz"),
                    backend=None if tts_backend == "auto" else str(tts_backend),
                    allow_network_fallback=tts_allow_network_fallback,
                )
                log(f"  vocal_color dur={color_dur:.2f}s gain={color_gain:.2f}")
            except Exception as exc:  # noqa: BLE001 — color is soft layer
                log(f"  vocal_color skip {sid}: {exc}")
                color_wav = None
                color_dur = 0.0
        # shorter tail — snappier cut to next shot
        pad = float(getattr(args, "vo_pad", 0.12) or 0.12)
        target = dur + pad
        # visual_fit: "slot" locks to duration_sec; "vo" follows VO length.
        # P0 · 2026-07-23: default for voice_coupled / short I2V is vo-timed so we
        # do not pad 6s clips to 7–8s plates (stream_loop double-play / long freeze).
        # See lessons-2026-07-20-action-fluency.md · shortform_no_double_play.
        es = spec.get("edit_strategy") if isinstance(spec.get("edit_strategy"), dict) else {}
        es_mode = str(es.get("mode") or "").strip().lower()
        default_fit = "vo" if es_mode in {"voice_coupled", "punchy"} else "slot"
        visual_fit = str(spec.get("visual_fit") or default_fit).strip().lower()
        try:
            slot = float(shot.get("duration_sec") or 0)
        except (TypeError, ValueError):
            slot = 0.0
        # Per-shot override: shot.visual_fit or continue mid_motion prefers vo-timed
        shot_fit = str(shot.get("visual_fit") or "").strip().lower()
        dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
        cut_on = str(dsl.get("cut_on") or "").strip().lower()
        if shot_fit in {"vo", "slot"}:
            use_fit = shot_fit
        elif visual_fit == "vo" or cut_on == "mid_motion":
            use_fit = "vo"
        else:
            use_fit = visual_fit if visual_fit in {"vo", "slot"} else default_fit

        vo_atempo_plan: dict[str, Any] | None = None
        raw_vo_dur = float(dur)
        # vo_fit: atempo (default for slot) | legacy (pad/trim only, stretch video to VO)
        vo_fit = (
            str(spec.get("vo_fit") or getattr(args, "vo_fit", None) or "atempo").strip().lower()
        )
        if vo_fit not in {"atempo", "legacy"}:
            vo_fit = "atempo"

        if use_fit == "slot" and slot > 0 and vo_fit == "atempo":
            # Three-axis: plate = duration_sec; VO atempo to plate; video stretch only to plate
            try:
                from vo_atempo import VoAtempoError, fit_voice_to_plate, plan_vo_atempo

                plate = float(slot)
                plan = plan_vo_atempo(raw_vo_dur, plate)
                if not plan.get("ok"):
                    raise RenderError(
                        f"{sid} vo_atempo: {plan.get('note')} "
                        f"(vo={raw_vo_dur:.2f}s plate={plate:.2f}s). "
                        "Shorten nar, raise duration_sec, or --vo-fit legacy (discouraged)."
                    )
                fitted_wav = work / f"vo_fit_{i:02d}_{sid}.wav"
                vo_atempo_plan = fit_voice_to_plate(
                    wav,
                    fitted_wav,
                    plate,
                    vo_sec=raw_vo_dur,
                    plan=plan,
                    sample_rate=SR,
                )
                wav = fitted_wav
                dur = plate
                target = plate
                log(
                    f"  vo_atempo mode={plan.get('mode')} factor={plan.get('atempo')} "
                    f"raw={raw_vo_dur:.2f}s → plate={plate:.2f}s "
                    f"(video stays plate; no stretch-to-VO)"
                )
            except VoAtempoError as exc:
                raise RenderError(f"{sid} vo_atempo failed: {exc}") from exc
        elif use_fit != "vo" and slot > target:
            # legacy slot: expand timeline to plate without atempo
            target = slot
        # Optional edit handle: only play [in_point, out_point) of source plate
        try:
            out_point = (
                float(shot["out_point_sec"]) if shot.get("out_point_sec") is not None else None
            )
        except (TypeError, ValueError):
            out_point = None
        try:
            in_point = float(shot["in_point_sec"]) if shot.get("in_point_sec") is not None else None
        except (TypeError, ValueError):
            in_point = None
        shot_audio.append(
            {
                "id": sid,
                "text": text,
                "units": units,
                "wav": wav,
                "vo_dur": dur,
                "raw_vo_dur": raw_vo_dur,
                "target": target,
                "clip": clip_path,
                "title": shot.get("title") or sid,
                "tts": tts_meta,
                "native_audio": native_audio,
                "visual_fit": use_fit,
                "vo_fit": vo_fit if use_fit == "slot" else "n/a",
                "vo_atempo_plan": vo_atempo_plan,
                "out_point_sec": out_point,
                "in_point_sec": in_point,
                "color_wav": color_wav,
                "color_dur": color_dur,
                "color_text": color_text,
                "color_gain": color_gain if color_wav else 0.0,
                "color_offset_sec": color_payload.get("offset_sec", -1.0),
                "color_tts": color_meta,
                "color_source": color_payload.get("source"),
            }
        )

    # 2) Stretch each clip to VO length, then optional lip-sync on talking shots
    lipsync_report: list[dict[str, Any]] = []
    stretched: list[Path] = []
    shots_by_id = {shot.get("id"): shot for shot in shots}
    for i, item in enumerate(shot_audio):
        out = work / f"v_{i:02d}_{item['id']}.mp4"
        log(f"stretch {item['id']} -> {item['target']:.2f}s")
        shot_meta = shots_by_id.get(item["id"], {})
        beat = shot_meta.get("dramatic_function") if isinstance(shot_meta, dict) else None
        stretch_plan = stretch_clip(
            item["clip"],
            out,
            target=item["target"],
            width=width,
            height=height,
            fps=fps,
            dramatic_function=str(beat) if beat else None,
            in_point_sec=item.get("in_point_sec"),
            out_point_sec=item.get("out_point_sec"),
        )
        item["stretch_plan"] = stretch_plan
        # Keep VO/join clock aligned when stretch clamps target (anti double-play)
        eff = stretch_plan.get("effective_target")
        if eff is not None:
            try:
                eff_f = float(eff)
                if eff_f > 0 and abs(eff_f - float(item["target"])) > 0.04:
                    log(
                        f"  clamp target {item['target']:.2f}s → {eff_f:.2f}s "
                        f"({stretch_plan.get('clamp_reason') or 'stretch'})"
                    )
                    item["target"] = eff_f
                    item["vo_dur"] = min(float(item.get("vo_dur") or eff_f), eff_f)
            except (TypeError, ValueError):
                pass
        log(
            f"  stretch mode={stretch_plan.get('mode')} loops={stretch_plan.get('loops')} "
            f"freeze={stretch_plan.get('freeze_sec')}"
        )

        shot_meta = shots_by_id.get(item["id"], {})
        want_ls = False
        if lipsync_mode != "off" and should_lipsync_shot is not None:
            want_ls = should_lipsync_shot(shot_meta)
        if want_ls and lipsync_one is not None and lipsync_mode != "off":
            ls_out = work / f"v_{i:02d}_{item['id']}_lipsync.mp4"
            backend = "require" if lipsync_mode == "require" else lipsync_mode
            # Prefer keyframe still for free Wav2Lip talking-head quality when available
            face_src = out
            kf = keyframes_dir / f"{item['id']}.jpg"
            if not kf.is_file():
                for ext in (".png", ".jpeg", ".webp"):
                    alt = keyframes_dir / f"{item['id']}{ext}"
                    if alt.is_file():
                        kf = alt
                        break
            if kf.is_file():
                face_src = kf
            try:
                log(f"lipsync {item['id']} face={face_src.name} backend={backend}...")
                result = lipsync_one(
                    video=face_src,
                    audio=item["wav"],
                    out=ls_out,
                    backend=backend if backend != "require" else "require",
                )
                if result.get("ok") and ls_out.is_file():
                    # Strip embedded audio; final mix uses narration+BGM stems
                    ls_video_only = work / f"v_{i:02d}_{item['id']}_ls_v.mp4"
                    run(
                        [
                            "ffmpeg",
                            "-y",
                            "-i",
                            str(ls_out),
                            "-an",
                            "-c:v",
                            "libx264",
                            "-preset",
                            "fast",
                            "-crf",
                            "20",
                            "-pix_fmt",
                            "yuv420p",
                            "-t",
                            f"{item['target']:.3f}",
                            str(ls_video_only),
                        ]
                    )
                    out = ls_video_only
                    lipsync_report.append({"id": item["id"], **result})
                else:
                    lipsync_report.append(
                        {
                            "id": item["id"],
                            "ok": False,
                            "skipped": True,
                            "detail": result,
                        }
                    )
                    if lipsync_mode == "require":
                        raise RenderError(
                            f"lipsync required but skipped for {item['id']}: {result}"
                        )
            except Exception as exc:
                lipsync_report.append({"id": item["id"], "ok": False, "error": str(exc)})
                if lipsync_mode == "require":
                    raise RenderError(f"lipsync failed for {item['id']}: {exc}") from exc
                log(f"lipsync skip {item['id']}: {exc}")
        stretched.append(out)

    # 3) Title / end cards
    # plate_cards=blank: keep pad duration for VO/SRT clock, no burned glyphs
    # (designed-post HyperFrames/Remotion draws the readable title once).
    plate_cards = str(getattr(args, "plate_cards", "text") or "text").strip().lower()
    if plate_cards not in {"text", "blank"}:
        raise RenderError("--plate-cards must be text|blank")
    title_text = args.title or spec.get("title") or manifest.get("title") or "AI Film"
    end_text = args.end_title or "— 完 —"
    title_mp4 = work / "title.mp4"
    end_mp4 = work / "end.mp4"
    title_dur = float(args.title_dur)
    end_dur = float(args.end_dur)
    title_draw = "" if plate_cards == "blank" else str(title_text)
    end_draw = "" if plate_cards == "blank" else str(end_text)
    if title_dur > 0.01:
        mkcard_video(
            title_draw,
            title_mp4,
            width=width,
            height=height,
            duration=title_dur,
            fps=fps,
            font_path=font_path,
        )
    if end_dur > 0.01:
        mkcard_video(
            end_draw,
            end_mp4,
            width=width,
            height=height,
            duration=end_dur,
            fps=fps,
            font_path=font_path,
        )

    # 4) Concat video parts: title + shots + end (per-join hard/soft/hold)
    try:
        transition_sec = normalize_transition_sec(
            getattr(args, "transition_sec", None)
            if getattr(args, "transition_sec", None) is not None
            else spec.get("transition_sec", DEFAULT_TRANSITION_SEC)
        )
    except PolicyError as exc:
        raise RenderError(str(exc)) from exc
    story_intents = spec.get("transition_intents")
    if story_intents is not None and not isinstance(story_intents, list):
        raise RenderError("film-spec transition_intents must be an array")
    default_intent = str(spec.get("transition_default") or "soft")
    try:
        full_join_intents = expand_story_join_intents(
            len(shot_audio),
            story_intents=list(story_intents) if story_intents is not None else None,
            default_intent=default_intent if transition_sec > 0 else "hard",
            edge_intent=default_intent if transition_sec > 0 else "hard",
        )
    except PolicyError as exc:
        raise RenderError(str(exc)) from exc
    parts: list[Path] = []
    if title_dur > 0.01:
        parts.append(title_mp4)
    parts.extend(stretched)
    if end_dur > 0.01:
        parts.append(end_mp4)
    silent = work / "video_silent.mp4"
    transition_style = str(spec.get("transition_style") or "fade").strip().lower() or "fade"
    story_styles = spec.get("transition_styles")
    if story_styles is not None and not isinstance(story_styles, list):
        raise RenderError("film-spec transition_styles must be an array")
    try:
        full_join_styles = expand_story_join_styles(
            len(shot_audio),
            story_styles=[str(x) for x in story_styles] if story_styles is not None else None,
            edge_style=transition_style,
        )
    except PolicyError as exc:
        raise RenderError(str(exc)) from exc
    # Per-join transition duration from edit_strategy (voice-coupled rhythm)
    full_join_use_ts: list[float] | None = None
    raw_join_secs = spec.get("join_transition_secs")
    if isinstance(raw_join_secs, list) and len(raw_join_secs) == len(shot_audio) - 1:
        try:
            story_secs = [max(0.0, min(0.8, float(x))) for x in raw_join_secs]
            edge = float(transition_sec) if transition_sec > 0 else 0.05
            # title→s0, s0→s1…, sN→end  (len = n_shots + 1 when both pads present)
            n_parts = len(parts)
            n_joins = max(0, n_parts - 1)
            if n_joins == len(shot_audio) + 1:
                full_join_use_ts = [edge] + story_secs + [edge]
            elif n_joins == len(shot_audio):
                # missing one pad
                full_join_use_ts = [edge] + story_secs
            elif n_joins == len(shot_audio) - 1:
                full_join_use_ts = story_secs
            else:
                full_join_use_ts = None
            if full_join_use_ts is not None and len(full_join_use_ts) != n_joins:
                full_join_use_ts = None
        except (TypeError, ValueError):
            full_join_use_ts = None
    xfade_plan = concat_videos(
        parts,
        silent,
        transition_sec=transition_sec,
        fps=fps,
        join_intents=full_join_intents,
        transition_style=transition_style,
        join_styles=full_join_styles,
        join_use_ts=full_join_use_ts,
    )
    log(
        f"video concat method={xfade_plan.get('method')} transition_sec={transition_sec} "
        f"style={transition_style} styles={xfade_plan.get('join_styles')} "
        f"join_use_ts={full_join_use_ts} "
        f"enabled={xfade_plan.get('enabled')} joins={full_join_intents}"
    )

    # 5) Build narration track with title/end silence + acrossfade matching video
    sil_t = work / "sil_t.wav"
    sil_e = work / "sil_e.wav"
    silence_wav(sil_t, title_dur)
    silence_wav(sil_e, end_dur)
    voice_inputs = [sil_t] + [item["wav"] for item in shot_audio] + [sil_e]
    # convert each to same format and pad to exact segment durations
    voice_parts: list[Path] = []
    segs_durs = [title_dur] + [item["target"] for item in shot_audio] + [end_dur]
    for i, (src, dur) in enumerate(zip(voice_inputs, segs_durs, strict=False)):
        part = work / f"vo_part_{i:02d}.wav"
        # pad/trim to exact duration
        run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(src),
                "-af",
                f"apad=pad_dur={dur:.3f},atrim=0:{dur:.3f},asetpts=PTS-STARTPTS",
                "-ar",
                str(SR),
                "-ac",
                "1",
                "-c:a",
                "pcm_s16le",
                str(part),
            ]
        )
        voice_parts.append(part)
    try:
        voice_cat = safe_output_path(
            audio_dir, "narration.wav", suffixes={".wav"}, field="narration output"
        )
    except SecurityPolicyError as exc:
        raise RenderError(str(exc)) from exc
    active_transition = transition_sec if xfade_plan.get("enabled") else 0.0
    audio_join_intents = (
        full_join_intents if xfade_plan.get("enabled") else ["hard"] * max(0, len(segs_durs) - 1)
    )
    # Placeholder to keep following code structure: voice_cat filled by acrossfade
    afade_plan = concat_audio_segments(
        voice_parts,
        voice_cat,
        transition_sec=active_transition,
        segment_durs=segs_durs,
        join_intents=audio_join_intents if xfade_plan.get("enabled") else None,
    )
    log(f"audio concat method={afade_plan.get('method')}")
    total_dur = pdur(voice_cat)
    native_track = build_native_track(
        shot_audio,
        title_duration=title_dur,
        end_duration=end_dur,
        work=work,
        audio_dir=audio_dir,
        transition_sec=active_transition,
        join_intents=audio_join_intents if xfade_plan.get("enabled") else None,
    )

    # 6) Music
    try:
        music_path = safe_output_path(
            audio_dir, "bgm_procedural.wav", suffixes={".wav"}, field="BGM output"
        )
    except SecurityPolicyError as exc:
        raise RenderError(str(exc)) from exc
    mix_spotting: dict[str, Any] = {
        "mood": mood,
        "bed": True,
        "applied_events": [],
        "total_duration": float(total_dur),
        "event_count": 0,
        "bed_applied": True,
        "voice_tracks": {
            "nar_gain": vo_gain,
            "vocal_color_gain": film_vocal_color_gain,
            "native_audio_volume": native_audio_volume,
            "policy": voice_policy,
        },
    }
    # Spotting map shared by procedural + user music (mute/duck/sfx on bed)
    spot_shot_targets = [float(item["target"]) for item in shot_audio]
    spot_tl = film_segment_timeline(
        title_duration=title_dur,
        shot_targets=spot_shot_targets,
        end_duration=end_dur,
        transition_sec=active_transition,
        story_join_intents=list(story_intents) if story_intents is not None else None,
        default_intent=default_intent if active_transition > 0 else "hard",
    )
    shot_start_map = {
        str(item["id"]): float(spot_tl["shot_starts"][i]) for i, item in enumerate(shot_audio)
    }
    # film_segment_timeline returns shot_starts only; durations stay in spot_shot_targets
    shot_end_map = {
        str(item["id"]): float(spot_tl["shot_starts"][i] + spot_shot_targets[i])
        for i, item in enumerate(shot_audio)
    }
    sound_plan = spec.get("sound_plan") if isinstance(spec.get("sound_plan"), dict) else None
    if sound_plan is None:
        sound_plan = {}
    # Auto light SFX accents from dramatic_function when author left events empty
    flat = {str(s["id"]): s for s in flatten_shots(spec) if isinstance(s, dict) and s.get("id")}
    shot_dicts = [flat.get(str(item["id"]), {"id": item["id"]}) for item in shot_audio]
    heat_scale = str(spec.get("heat_scale") or "").strip().lower() or None
    sound_plan = inject_auto_sfx_if_empty(sound_plan, shot_dicts, heat_scale=heat_scale)
    # sound_cues on shots → extra sfx_accent events (声景轨，不进旁白)
    if sound_cues_to_sfx_kinds is not None and isinstance(sound_plan, dict):
        cue_events: list[dict[str, Any]] = list(sound_plan.get("events") or [])
        added = 0
        for sh in shot_dicts:
            if not isinstance(sh, dict):
                continue
            kinds = sh.get("_sfx_kinds_from_cues") or sound_cues_to_sfx_kinds(
                sh.get("sound_cues") or []
            )
            for kind in list(kinds)[:2]:
                cue_events.append(
                    {
                        "type": "sfx_accent",
                        "shot_id": sh.get("id"),
                        "kind": kind,
                        "source": "sound_cues",
                    }
                )
                added += 1
        if added:
            sound_plan = {**sound_plan, "events": cue_events}
            notes = list(sound_plan.get("_notes") or [])
            notes.append(f"sound_cues: injected {added} sfx_accent(s)")
            sound_plan["_notes"] = notes

    # vocal_color timeline stem (after shot_starts known); default off → None
    color_track = build_vocal_color_track(
        shot_audio,
        shot_start_map=shot_start_map,
        total_duration=float(total_dur),
        work=work,
        audio_dir=audio_dir,
    )
    if color_track is not None:
        mix_spotting["vocal_color_track"] = str(color_track)
        mix_spotting["vocal_color_shots"] = [
            {
                "id": it.get("id"),
                "text": it.get("color_text"),
                "gain": it.get("color_gain"),
                "source": it.get("color_source"),
            }
            for it in shot_audio
            if it.get("color_wav")
        ]
        log(f"vocal_color track: {len(mix_spotting['vocal_color_shots'])} stem(s)")
    else:
        mix_spotting["vocal_color_track"] = None
        mix_spotting["vocal_color_shots"] = []
        log("vocal_color track: off (nar+BGM dominate; opt-in via voice_tracks.enabled)")

    def _apply_spotting_and_convert_to_stereo(
        float_bed: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
        """mute/duck on bgm bed, sfx_accent on sfx bed (upmixes mono to stereo)."""
        spotting: dict[str, Any]
        try:
            spotting = expand_sound_events(
                sound_plan,
                shot_starts=shot_start_map,
                total_duration=float(total_dur),
            )
        except SoundPlanError as exc:
            raise RenderError(str(exc)) from exc
        events = spotting.get("applied_events") or []

        if float_bed.ndim == 1:
            bgm_out = np.column_stack((float_bed, float_bed))
        elif float_bed.ndim == 2 and float_bed.shape[1] == 1:
            bgm_out = np.column_stack((float_bed[:, 0], float_bed[:, 0]))
        else:
            bgm_out = float_bed.copy()

        sfx_out = np.zeros_like(bgm_out)

        if events:
            bgm_out = apply_mute_windows_to_samples(bgm_out, sr=SR, events=events)
            sfx_out = apply_sfx_accents_to_samples(sfx_out, sr=SR, events=events, level=0.55)
            bgm_out = np.clip(bgm_out, -1.0, 1.0)
            sfx_out = np.clip(sfx_out, -1.0, 1.0)
            spotting["sfx_overlay_count"] = sum(
                1 for e in events if e.get("type") == "sfx_accent" and e.get("overlay_applied")
            )
        else:
            spotting["sfx_overlay_count"] = 0
        spotting["bed_source"] = spotting.get("bed_source") or "unknown"
        return bgm_out, sfx_out, spotting

    # Anti-fatigue seed first (pool pick + procedural style share it)
    plan_mood = (sound_plan or {}).get("mood") if sound_plan else None
    if plan_mood:
        mood = str(plan_mood)
    seed_arg = getattr(args, "music_seed", None)
    policy_seed = None
    ap = spec.get("audio_policy") if isinstance(spec.get("audio_policy"), dict) else {}
    if ap.get("music_seed") is not None:
        try:
            policy_seed = int(ap["music_seed"])
        except (TypeError, ValueError):
            policy_seed = None
    if seed_arg is not None:
        music_seed = int(seed_arg)
    elif policy_seed is not None:
        music_seed = policy_seed
    else:
        title_s = str(spec.get("title") or root.name)
        # v3: style families; include recipe summary so different arcs reshuffle beds
        route = spec.get("_audio_routing") if isinstance(spec.get("_audio_routing"), dict) else {}
        counts = route.get("counts") if isinstance(route.get("counts"), dict) else {}
        count_key = ",".join(f"{k}{counts.get(k, 0)}" for k in sorted(counts))
        raw_seed = f"{title_s}|{mood}|{total_dur:.2f}|v3-multi-style|{count_key}"
        music_seed = int(hashlib.sha256(raw_seed.encode("utf-8")).hexdigest()[:8], 16)

    # Phase 4: Plot-Adaptive Mood Timeline
    if isinstance(sound_plan, dict):
        sound_plan["mood_timeline"] = build_mood_timeline(
            shot_dicts, shot_starts=shot_start_map, shot_ends=shot_end_map, default_mood=mood
        )

    # Phase H: local template pool (audio/bgm.wav or assets/bgm/{mood}/*)
    try:
        music_resolved = resolve_music_template(
            root,
            mood=mood,
            plan=sound_plan if isinstance(sound_plan, dict) else None,
            music_arg=getattr(args, "music", None),
            mode=getattr(args, "music_template", None),
            music_license=getattr(args, "music_license", None),
            seed=music_seed,
        )
    except SoundPlanError as exc:
        raise RenderError(str(exc)) from exc

    # Optional external AI music (ACE-Step / MusicGen…) when no local bed
    if music_resolved is None:
        ext_music = _try_external_music_gen(
            work=work,
            duration=total_dur,
            mood=mood,
            seed=music_seed,
            title=str(spec.get("title") or root.name),
        )
        if ext_music is not None:
            music_resolved = ext_music

    mix_spotting["music_template"] = (
        {
            "source": music_resolved.get("source"),
            "path": music_resolved.get("relative") or music_resolved.get("path"),
            "mode": music_resolved.get("mode"),
            "pool_size": music_resolved.get("pool_size"),
            "pool_index": music_resolved.get("pool_index"),
        }
        if music_resolved
        else {"source": "procedural", "mode": getattr(args, "music_template", None) or "auto"}
    )
    mix_spotting["music_seed"] = music_seed

    if music_resolved and Path(music_resolved["path"]).is_file():
        music_src = Path(music_resolved["path"]).expanduser().resolve()
        license_note = str(music_resolved.get("license_note") or "user-supplied file")
        mono_tmp = work / "bgm_user_mono.wav"
        # loop/trim to total mono for spotting, then stereo
        run(
            [
                "ffmpeg",
                "-y",
                "-stream_loop",
                "-1",
                "-i",
                str(music_src),
                "-t",
                f"{total_dur:.3f}",
                "-ar",
                str(SR),
                "-ac",
                "1",
                "-c:a",
                "pcm_s16le",
                str(mono_tmp),
            ]
        )
        # load mono int16
        with wave.open(str(mono_tmp), "rb") as handle:
            frames = handle.readframes(handle.getnframes())
            user_i16 = np.frombuffer(frames, dtype=np.int16).astype(np.float64) / 32767.0
        user_f, sfx_f, spotting_only = _apply_spotting_and_convert_to_stereo(user_i16)
        # keep multi-track voice metadata (not wiped by bed spotting)
        mix_spotting = {**mix_spotting, **spotting_only}
        mix_spotting["mood"] = (sound_plan or {}).get("mood", mood) if sound_plan else mood
        mix_spotting["bed_source"] = str(music_resolved.get("source") or "user_music_file")
        mix_spotting["music_seed"] = music_seed
        mix_spotting["note"] = "user/external music — mute/duck on bgm, sfx separated"
        if sound_plan and sound_plan.get("bed") is False:
            user_f = np.zeros_like(user_f)
            mix_spotting["bed_applied"] = False
        else:
            mix_spotting["bed_applied"] = True
        stereo = work / "bgm_stereo.wav"
        sfx_stereo_path = work / "sfx_stereo.wav"
        write_wav_stereo(stereo, (np.clip(user_f, -1.0, 1.0) * 32767.0).astype(np.int16))
        write_wav_stereo(sfx_stereo_path, (np.clip(sfx_f, -1.0, 1.0) * 32767.0).astype(np.int16))
        music_path = stereo
    else:
        license_note = "original generative numpy score (ai-film-grok procedural v3 multi-style, no third-party samples)"
        # IMPORTANT: generate BGM at fixed healthy amp — do NOT multiply by music_volume here
        # (music_volume is applied once in the dual-track mix below)
        gen_amp = float(getattr(args, "bgm_gen_amp", None) or DEFAULT_BGM_GEN_AMP)
        bg_hint = 1.0
        try:
            bg_hint = float(
                (sound_plan or {}).get("bed_gain_hint")
                or (spec.get("_audio_routing") or {}).get("mean_bed_gain")
                or 1.0
            )
        except (TypeError, ValueError):
            bg_hint = 1.0
        s_starts = []
        acc = title_dur
        for item in shot_audio:
            s_starts.append(acc)
            acc += float(item.get("target") or 6.0)

        samples = procedural_music(
            total_dur,
            emo=1.1,
            curve="swell",
            amp=gen_amp,
            mood=mood,
            seed=music_seed,
            shot_starts=s_starts,
            events=(sound_plan or {}).get("events"),
            mood_timeline=(sound_plan or {}).get("mood_timeline"),
        )
        float_bed = samples.astype(np.float64) / 32767.0
        float_bed, sfx_f, spotting_only = _apply_spotting_and_convert_to_stereo(float_bed)
        mix_spotting = {**mix_spotting, **spotting_only}
        mix_spotting["bed_source"] = "procedural"
        mix_spotting["music_seed"] = music_seed
        mix_spotting["bed_gain_hint"] = bg_hint
        try:
            from make_sfx_bed import last_rnb_style, pick_rnb_style  # type: ignore

            mix_spotting["procedural_style"] = last_rnb_style() or pick_rnb_style(music_seed)
        except Exception:
            mix_spotting["procedural_style"] = "unknown"
        log(
            f"BGM procedural seed={music_seed} style={mix_spotting.get('procedural_style')} "
            f"(change --music-seed for another take/style)"
        )
        if sound_plan and sound_plan.get("bed") is False:
            float_bed = np.zeros_like(float_bed)
            mix_spotting["bed_applied"] = False
        else:
            mix_spotting["bed_applied"] = True
        stereo = work / "bgm_stereo.wav"
        sfx_stereo_path = work / "sfx_stereo.wav"
        write_wav_stereo(stereo, (np.clip(float_bed, -1.0, 1.0) * 32767.0).astype(np.int16))
        write_wav_stereo(sfx_stereo_path, (np.clip(sfx_f, -1.0, 1.0) * 32767.0).astype(np.int16))
        music_path = stereo

    # 7) Dual-track mix: VO primary + BGM always audible (两条音轨)
    # Sidechain: rnb default longer release so groove returns in VO pauses (Phase E)
    try:
        mixed = safe_output_path(
            audio_dir, "mixed.wav", suffixes={".wav"}, field="mixed audio output"
        )
    except SecurityPolicyError as exc:
        raise RenderError(str(exc)) from exc
    music_vol = float(args.music_volume)
    # Recipe bed_gain also nudges mix music_volume once (author CLI still wins base)
    try:
        bg_hint = float(
            (sound_plan or {}).get("bed_gain_hint")
            or (spec.get("_audio_routing") or {}).get("mean_bed_gain")
            or 1.0
        )
        if abs(bg_hint - 1.0) > 0.02:
            music_vol = max(0.02, min(1.0, music_vol * bg_hint))
            mix_spotting["music_vol_after_recipe"] = music_vol
    except (TypeError, ValueError):
        pass
    if isinstance(spec.get("_audio_routing"), dict):
        mix_spotting["audio_routing_counts"] = (spec.get("_audio_routing") or {}).get("counts")
        mix_spotting["audio_policy"] = (spec.get("audio_policy") or {}).get("mode")
    sc_overrides = {
        "threshold": getattr(args, "sidechain_threshold", None),
        "ratio": getattr(args, "sidechain_ratio", None),
        "attack_ms": getattr(args, "sidechain_attack", None),
        "release_ms": getattr(args, "sidechain_release", None),
    }
    try:
        sidechain = resolve_sidechain(
            sound_plan if isinstance(sound_plan, dict) else None,
            mood=mood,
            overrides=sc_overrides,
        )
    except SoundPlanError as exc:
        raise RenderError(str(exc)) from exc
    mix_spotting["sidechain"] = sidechain
    sc_frag = sidechain_filter_fragment(sidechain)
    filters_help = run(["ffmpeg", "-filters"], check=False).stdout

    try:
        from acoustic_policy import resolve_acoustic_space

        v_motifs = (spec.get("director_intent") or {}).get("visual_motifs") or []
        loc_tags = [str(x) for x in v_motifs]
        ac = resolve_acoustic_space(loc_tags)
        # P0 · 2026-07-23: aecho on full ~60s stems hung ffmpeg 50+ min (wall clock).
        # Keep EQ only; reverb can be opt-in via film-spec acoustic_reverb=true later.
        sfx_dsp = f"highpass=f={ac['highpass']},lowpass=f={ac['lowpass']}"
        if bool((spec.get("audio_policy") or {}).get("acoustic_reverb")) or bool(
            os.environ.get("AIFILM_SFX_REVERB", "").strip() in {"1", "true", "yes"}
        ):
            sfx_dsp += f",aecho=1.0:1.0:{ac['reverb_time'] * 1000}:{ac['wet_level']}"
    except Exception:
        sfx_dsp = "anull"
    mix_spotting["sfx_dsp_applied"] = sfx_dsp

    use_color = color_track is not None and Path(str(color_track)).is_file()
    color_in_gain = 1.0  # per-stem gain already applied in build_vocal_color_track

    fc_parts = [
        f"[0:a]volume={vo_gain:.3f},aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[narr]",
        f"[1:a]volume={music_vol:.3f},aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[mus]",
        f"[2:a]volume={native_audio_volume:.3f},aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[native]",
        f"[3:a]volume=1.0,aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,{sfx_dsp}[sfx]",
    ]
    if use_color:
        fc_parts.append(
            f"[4:a]volume={color_in_gain:.3f},aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[color]"
        )

    if "sidechaincompress" in filters_help and "acrossover" in filters_help:
        fc_parts.append("[mus]acrossover=split=300 4000[mus_l][mus_m][mus_h]")
        fc_parts.append("[narr]asplit[narr_main][narr_sc]")
        fc_parts.append(f"[mus_m][narr_sc]{sc_frag}[mus_m_ducked]")
        fc_parts.append(
            "[mus_l][mus_m_ducked][mus_h]amix=inputs=3:duration=longest:normalize=0[mus_ducked]"
        )
        fc_parts.append("[mus_ducked][native][sfx]amix=inputs=3:duration=longest:normalize=0[bed]")
        final_amix_count = 2 + (1 if use_color else 0)
        color_in = "[color]" if use_color else ""
        fc_parts.append(
            f"[narr_main][bed]{color_in}amix=inputs={final_amix_count}:duration=first:normalize=0,alimiter=limit=0.95[aout]"
        )
        mix_spotting["sidechain_applied"] = "dynamic_eq"
    elif "sidechaincompress" in filters_help:
        fc_parts.append("[mus][native][sfx]amix=inputs=3:duration=longest:normalize=0[bed]")
        fc_parts.append(f"[bed][narr]{sc_frag}[ducked]")
        final_amix_count = 2 + (1 if use_color else 0)
        color_in = "[color]" if use_color else ""
        fc_parts.append(
            f"[narr][ducked]{color_in}amix=inputs={final_amix_count}:duration=first:normalize=0,alimiter=limit=0.95[aout]"
        )
        mix_spotting["sidechain_applied"] = "broadband"
    else:
        final_amix_count = 4 + (1 if use_color else 0)
        color_in = "[color]" if use_color else ""
        fc_parts.append(
            f"[narr][mus][native][sfx]{color_in}amix=inputs={final_amix_count}:duration=first:normalize=0,alimiter=limit=0.95[aout]"
        )
        mix_spotting["sidechain_applied"] = False

    fc = ";".join(fc_parts)
    mix_spotting["mix_inputs"] = ["narration", "bgm", "native", "sfx"] + (
        ["vocal_color"] if use_color else []
    )

    try:
        mix_report_path = safe_output_path(
            audio_dir, "mix_report.json", suffixes={".json"}, field="mix report"
        )
        atomic_write_text(
            mix_report_path,
            json.dumps(mix_spotting, ensure_ascii=False, indent=2) + "\n",
        )
        mix_spotting["report_path"] = str(mix_report_path)
    except SecurityPolicyError as exc:
        raise RenderError(str(exc)) from exc

    mix_cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(voice_cat),
        "-i",
        str(music_path),
        "-i",
        str(native_track),
        "-i",
        str(sfx_stereo_path),
    ]
    if use_color:
        mix_cmd.extend(["-i", str(color_track)])
    mix_cmd.extend(
        [
            "-filter_complex",
            fc,
            "-map",
            "[aout]",
            "-ar",
            "44100",
            "-ac",
            "2",
            "-c:a",
            "pcm_s16le",
            str(mixed),
        ]
    )
    run(mix_cmd)

    # Phase F/G: loudness probe + optional/auto loudnorm toward shortform target
    try:
        loud_policy = resolve_loudnorm(
            sound_plan if isinstance(sound_plan, dict) else None,
            mode=getattr(args, "loudnorm", None),
            target_lufs=getattr(args, "target_lufs", None),
        )
    except SoundPlanError as exc:
        raise RenderError(str(exc)) from exc
    mix_spotting["loudnorm_policy"] = loud_policy
    try:
        loud = probe_mixed_loudness(mixed)
        if loud:
            mix_spotting["loudness_before"] = loud
            mix_spotting["loudness"] = loud
        measured = (loud or {}).get("integrated_lufs") if loud else None
        apply_ln, ln_reason = should_apply_loudnorm(loud_policy, measured)
        mix_spotting["loudnorm_decision"] = {"apply": apply_ln, "reason": ln_reason}
        if apply_ln:
            tgt = float(loud_policy["target_lufs"])
            normed = work / "mixed_loudnorm.wav"
            log(f"loudnorm apply → I={tgt:.1f} LUFS ({ln_reason})")
            ln_proc = run(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    str(mixed),
                    "-af",
                    f"loudnorm=I={tgt:.1f}:TP=-1.5:LRA=11",
                    "-ar",
                    "44100",
                    "-ac",
                    "2",
                    "-c:a",
                    "pcm_s16le",
                    str(normed),
                ],
                check=False,
            )
            if ln_proc.returncode == 0 and normed.is_file() and normed.stat().st_size > 1000:
                import shutil as _shutil

                _shutil.copy2(normed, mixed)
                mix_spotting["loudnorm_applied"] = True
                loud_after = probe_mixed_loudness(mixed)
                if loud_after:
                    mix_spotting["loudness_after"] = loud_after
                    mix_spotting["loudness"] = loud_after
            else:
                mix_spotting["loudnorm_applied"] = False
                mix_spotting["loudnorm_error"] = (
                    ln_proc.stderr or ln_proc.stdout or "loudnorm failed"
                )[-400:]
        else:
            mix_spotting["loudnorm_applied"] = False
        mix_spotting["artifacts"] = {
            "bgm": {"path": str(music_path), "sha256": sha256(music_path)},
            "sfx": {"path": str(sfx_stereo_path), "sha256": sha256(sfx_stereo_path)},
            "mixed": {"path": str(mixed), "sha256": sha256(mixed)},
        }
        if mix_spotting.get("report_path"):
            atomic_write_text(
                Path(str(mix_spotting["report_path"])),
                json.dumps(mix_spotting, ensure_ascii=False, indent=2) + "\n",
            )
        validate_audio_tracks_contract(spec, audio_dir=audio_dir, require_artifacts=True)
    except SoundPlanError:
        raise
    except Exception as exc:  # pragma: no cover — probe must never fail final
        mix_spotting["loudness_error"] = str(exc)[:200]
        if mix_spotting.get("report_path"):
            with contextlib.suppress(Exception):
                atomic_write_text(
                    Path(str(mix_spotting["report_path"])),
                    json.dumps(mix_spotting, ensure_ascii=False, indent=2) + "\n",
                )

    # 8) Subtitle cues — char-weighted, early; same xfade clock as picture/VO/native
    sub_lead = float(getattr(args, "sub_lead", 0.08) or 0.0)  # show slightly before speech
    sub_min = float(getattr(args, "sub_min_unit", 0.48) or 0.48)
    sub_max = float(getattr(args, "sub_max_unit", 1.75) or 1.75)
    cues, film_tl = build_subtitle_cues_for_shots(
        shot_audio,
        title_duration=title_dur,
        end_duration=end_dur,
        transition_sec=active_transition,
        sub_lead=sub_lead,
        sub_min=sub_min,
        sub_max=sub_max,
        story_join_intents=list(story_intents) if story_intents is not None else None,
        default_intent=default_intent if active_transition > 0 else "hard",
    )

    try:
        srt_path = safe_output_path(
            out_dir, "final.srt", suffixes={".srt"}, field="subtitle sidecar"
        )
    except SecurityPolicyError as exc:
        raise RenderError(str(exc)) from exc
    write_srt(srt_path, cues)

    # Burn subs with PIL overlays (no drawtext dependency).
    # --subs off keeps SRT only (for HyperFrames designed captions underlay path).
    subs_mode = str(getattr(args, "subs", "burn") or "burn").strip().lower()
    if subs_mode not in {"burn", "off"}:
        raise RenderError("--subs must be burn|off")
    video_subbed = work / "video_subbed.mp4"
    if subs_mode == "off" or not cues:
        shutil.copy2(silent, video_subbed)
    else:
        overlay_inputs: list[str] = ["-i", str(silent)]
        filter_parts: list[str] = []
        last = "[0:v]"
        oidx = 1
        for i, cue in enumerate(cues):
            png = overlays_dir / f"sub_{i:03d}.png"
            shot_index = cue.get("shot_index", 0)
            shot = shot_dicts[shot_index] if shot_dicts and shot_index < len(shot_dicts) else {}
            safe_area = (shot.get("dsl") or {}).get("safe_area") or {}

            # Subtitles default to bottom, but we dodge to top if subtitle_clear is explicitly false
            dodge = safe_area.get("subtitle_clear") is False
            italic = cue.get("is_monologue", False)

            sub_png(
                cue["text"],
                png,
                width=width,
                height=height,
                font_path=font_path,
                dodge=dodge,
                italic=italic,
            )
            overlay_inputs += ["-i", str(png)]
            out_label = f"[o{i}]"
            filter_parts.append(
                f"{last}[{oidx}:v]overlay=0:0:enable='between(t,{cue['start']:.3f},{cue['end']:.3f})'{out_label}"
            )
            last = out_label
            oidx += 1
        if filter_parts:
            run(
                [
                    "ffmpeg",
                    "-y",
                    *overlay_inputs,
                    "-filter_complex",
                    ";".join(filter_parts),
                    "-map",
                    last,
                    "-c:v",
                    "libx264",
                    "-preset",
                    "fast",
                    "-crf",
                    "20",
                    "-pix_fmt",
                    "yuv420p",
                    str(video_subbed),
                ]
            )
        else:
            shutil.copy2(silent, video_subbed)

    # 9) Mux final
    run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(video_subbed),
            "-i",
            str(mixed),
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            str(final_path),
        ]
    )

    # Verify streams
    probe = run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "stream=codec_type,codec_name",
            "-of",
            "json",
            str(final_path),
        ]
    )
    streams = json.loads(probe.stdout).get("streams") or []
    has_v = any(s.get("codec_type") == "video" for s in streams)
    has_a = any(s.get("codec_type") == "audio" for s in streams)
    if not has_v or not has_a:
        raise RenderError("Final MP4 missing video or audio stream")

    timeline_path = root / "timeline.json"
    mix_report_path = root / "audio" / "mix_report.json"
    report = {
        "schema_version": 2,
        "created_at": utc_now(),
        "title": title_text,
        "output": str(final_path),
        "output_sha256": sha256(final_path),
        "duration_sec": pdur(final_path),
        "width": width,
        "height": height,
        "fps": fps,
        "vo_mode": vo_mode,
        "voice": voice,
        "transition": {
            "sec": transition_sec,
            "active_sec": active_transition,
            "story_intents": story_intents,
            "full_join_intents": full_join_intents,
            "default_intent": default_intent,
            "video": xfade_plan,
            "audio": afade_plan,
            "film_timeline": {
                "shot_starts": film_tl.get("shot_starts"),
                "output_duration": film_tl.get("output_duration"),
                "use_ts": film_tl.get("use_ts"),
                "enabled": film_tl.get("enabled"),
                "join_intents": film_tl.get("full_join_intents") or film_tl.get("join_intents"),
            },
        },
        "sound_spotting": mix_spotting,
        "tts": {
            "backend_requested": tts_backend,
            "probe": tts_info,
            "shots": [item.get("tts") for item in shot_audio],
        },
        "narration": {"path": str(voice_cat), "sha256": sha256(voice_cat)},
        "music": {
            "path": str(music_path),
            "sha256": sha256(music_path) if Path(music_path).is_file() else None,
            "license_or_source": license_note,
            "volume": music_vol,
            "ducked_under_narration": "sidechaincompress" in filters_help,
            "mood": mood,
        },
        "native_audio": {
            "path": str(native_track),
            "sha256": sha256(native_track),
            "volume": native_audio_volume,
            "preserved_shots": [item["id"] for item in shot_audio if item.get("native_audio")],
        },
        "audio_provenance": {
            "mix_report": str(mix_report_path) if mix_report_path.is_file() else None,
            "mix_report_sha256": sha256(mix_report_path) if mix_report_path.is_file() else None,
        },
        "timeline": {
            "path": str(timeline_path) if timeline_path.is_file() else None,
            "sha256": sha256(timeline_path) if timeline_path.is_file() else None,
        },
        "subtitles": {
            "srt": str(srt_path),
            "srt_sha256": sha256(srt_path),
            "cue_count": len(cues),
            "burned_in": subs_mode == "burn",
            "mode": subs_mode,
        },
        "shots": [
            {
                "id": item["id"],
                "text": item["text"],
                "vo_dur": item["vo_dur"],
                "raw_vo_dur": item.get("raw_vo_dur"),
                "target": item["target"],
                "stretch_plan": item.get("stretch_plan"),
                "vo_atempo_plan": item.get("vo_atempo_plan"),
                "visual_fit": item.get("visual_fit"),
                "vo_fit": item.get("vo_fit"),
                "tts": item.get("tts"),
            }
            for item in shot_audio
        ],
        "provider_visual": "grok-imagine",
        "post_engine": "ai-film-grok/render_final.py",
        "lipsync": {
            "mode": lipsync_mode,
            "probe": lipsync_probe() if lipsync_probe else None,
            "shots": lipsync_report,
        },
    }
    try:
        report_path = safe_output_path(
            out_dir, "final-delivery.json", suffixes={".json"}, field="delivery report"
        )
    except SecurityPolicyError as exc:
        raise RenderError(str(exc)) from exc
    write_json(report_path, report)

    try:
        technical_qa = analyze_media(final_path, require_audio=True, require_motion=True)
    except MediaQAError as exc:
        raise RenderError(str(exc)) from exc
    if not technical_qa.get("ok"):
        raise RenderError(f"Final MP4 failed technical QA: {technical_qa.get('errors')}")
    report["technical_qa"] = technical_qa
    write_json(report_path, report)

    # Update manifest gates
    manifest.setdefault("outputs", {})["final_film"] = {
        "path": str(final_path.name),  # store relative name when under out/
        "sha256": report["output_sha256"],
        "duration_sec": report["duration_sec"],
        "report": str(report_path.name),
        "assembled_at": utc_now(),
        "technical_qa": technical_qa,
    }
    # Technical success is not human/agent end-to-end approval.
    manifest.setdefault("gates", {})["final_complete"] = False
    manifest["updated_at"] = utc_now()
    write_json(root / "manifest.json", manifest)

    return {
        "ok": True,
        "output": str(final_path),
        "duration_sec": report["duration_sec"],
        "srt": str(srt_path),
        "report": str(report_path),
        "cue_count": len(cues),
        "music_license": license_note,
        "lipsync_shots": lipsync_report,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Render formal final film with VO + BGM + subs")
    p.add_argument("--root", required=True)
    p.add_argument("--out-name", default="film_final.mp4")
    p.add_argument("--voice", default=None, help="edge voice id or Fish reference_id")
    p.add_argument(
        "--tts-backend",
        default=None,
        choices=["auto", "minimax", "fish", "edge", "external"],
        help="TTS: auto prefers external > MiniMax > pinned Fish > edge",
    )
    p.add_argument(
        "--vo-rate", default=None, help='TTS rate e.g. "-5%%" (edge) / maps to Fish speed'
    )
    p.add_argument("--vo-pitch", default=None, help='TTS pitch e.g. "-1Hz" (edge only)')
    p.add_argument("--vo-gain", type=float, default=None, help="Narration mix gain (default 1.15)")
    p.add_argument(
        "--vocal-color-gain",
        type=float,
        default=None,
        help="Independent 娇喘/语助词 track mix gain (0..1.5; default 0 / off; opt-in with voice_tracks.enabled)",
    )
    p.add_argument("--title")
    p.add_argument("--end-title")
    p.add_argument("--title-dur", type=float, default=1.5)
    p.add_argument("--end-dur", type=float, default=1.6)
    p.add_argument(
        "--plate-cards",
        choices=["text", "blank"],
        default="text",
        help="text=FFmpeg burns title/end glyphs; blank=pad only (for HyperFrames/Remotion designed cards)",
    )
    p.add_argument(
        "--sub-lead", type=float, default=0.08, help="Show subtitles this many seconds early"
    )
    p.add_argument("--sub-min-unit", type=float, default=0.48)
    p.add_argument("--sub-max-unit", type=float, default=1.75)
    p.add_argument("--sub-max-chars", type=int, default=DEFAULT_SUB_MAX_CHARS)
    p.add_argument("--vo-pad", type=float, default=0.12)
    p.add_argument(
        "--vo-fit",
        default=None,
        choices=["atempo", "legacy"],
        help=(
            "slot visual_fit: atempo=VO speed to plate (cn three-axis, default); "
            "legacy=pad/trim only and may stretch video to VO"
        ),
    )
    p.add_argument(
        "--transition-sec",
        type=float,
        default=None,
        help=f"Inter-shot xfade/acrossfade seconds (default {DEFAULT_TRANSITION_SEC}; 0=hard cut)",
    )
    p.add_argument("--music", help="Optional external music file (overrides local templates)")
    p.add_argument(
        "--music-license",
        help="License note for --music or local template (or put audio/*.license.txt)",
    )
    p.add_argument(
        "--music-template",
        default=None,
        choices=["off", "auto", "on"],
        help="Local BGM: auto=use audio/bgm.wav or audio/templates/{mood}.* if present; on=require; off=procedural",
    )
    p.add_argument(
        "--music-volume",
        type=float,
        default=DEFAULT_MUSIC_VOLUME,
        help="BGM mix gain (once only). Dual-track: ~0.28-0.38 so BGM is audible under VO",
    )
    p.add_argument(
        "--native-audio-volume",
        type=float,
        default=None,
        help="Mix gain for original generated clip audio (0..1; default film-spec or 0.16)",
    )
    p.add_argument(
        "--music-mood",
        default="rnb",
        choices=["playful", "dark", "warm", "rnb", "sensual", "soul"],
        help="BGM mood; rnb/sensual/soul = seductive late-night R&B/Soul (色气默认，勿用 dark)",
    )
    p.add_argument(
        "--music-seed",
        type=int,
        default=None,
        help="Procedural BGM RNG seed (omit = stable hash of title+mood; change to hear a new take)",
    )
    p.add_argument(
        "--sidechain-threshold",
        type=float,
        help="VO→BGM sidechain threshold (default: rnb 0.065 / other 0.08)",
    )
    p.add_argument(
        "--sidechain-ratio",
        type=float,
        help="VO→BGM sidechain ratio (default: rnb 3.8 / other 3.5)",
    )
    p.add_argument(
        "--sidechain-attack",
        type=float,
        default=None,
        help="Sidechain attack ms (default: rnb 15 / other 20)",
    )
    p.add_argument(
        "--sidechain-release",
        type=float,
        help="Sidechain release ms — higher = BGM returns slower in VO pauses (rnb default 880)",
    )
    p.add_argument(
        "--loudnorm",
        default=None,
        choices=["off", "auto", "on"],
        help="Normalize mixed loudness: auto=only if too loud/quiet (default); on=always; off=never",
    )
    p.add_argument(
        "--target-lufs",
        type=float,
        default=None,
        help="loudnorm target integrated LUFS (default -16 shortform)",
    )
    p.add_argument(
        "--lipsync",
        default="off",
        choices=["auto", "off", "require", "external", "musetalk", "wav2lip"],
        help="Lip-sync OFF by default to avoid face collapse; opt-in with auto/wav2lip",
    )
    p.add_argument(
        "--allow-loop-risk",
        action="store_true",
        help="Allow final even when VO would stream_loop short plates (discouraged)",
    )
    p.add_argument(
        "--subs",
        default="burn",
        choices=["burn", "off"],
        help="burn=PIL burned captions (default); off=SRT only (HyperFrames designed captions)",
    )
    p.add_argument("--width", type=int)
    p.add_argument("--height", type=int)
    p.add_argument(
        "--export-stems",
        action="store_true",
        help="Export isolated VO, BGM, and SFX stems",
    )
    p.add_argument("--fps", type=int)
    args = p.parse_args(argv)
    try:
        # Explicit --music still requires license text OR sidecar (checked inside resolve)
        if args.music and not (args.music_license and args.music_license.strip()):
            # allow if sidecar will supply; soft check path exists near file
            p = Path(args.music).expanduser()
            side_ok = False
            try:
                from sound_plan import _license_sidecar_for

                side_ok = bool(_license_sidecar_for(p) if p.is_file() else False)
            except Exception:
                side_ok = False
            if not side_ok:
                raise RenderError(
                    "--music requires --music-license (or a sidecar "
                    f"{p.stem}.license.txt next to the file)"
                )
        result = render_final(args)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (RenderError, subprocess.CalledProcessError, ValueError) as exc:
        err = str(exc)
        if isinstance(exc, subprocess.CalledProcessError):
            err = (exc.stderr or exc.stdout or str(exc))[:2000]
        print(json.dumps({"ok": False, "error": err}, ensure_ascii=False, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

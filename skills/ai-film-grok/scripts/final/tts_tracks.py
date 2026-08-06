"""TTS synth + native/vocal-color track builders (R1c peel from render_final)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from edit_policy import PolicyError, normalize_transition_sec
from final.errors import RenderError
from final.media_ops import concat_audio_segments, pdur, run
from security_policy import SecurityPolicyError, safe_output_path

# Re-export-friendly defaults (render_final also keeps aliases for hard-compat)
SR = 44100
DEFAULT_VOCAL_COLOR_GAIN = 0.0  # 2026-07-21: 语助轨默认关闭；成片以 nar+BGM 主导

try:
    from tts_backend import synthesize as tts_synthesize
except ImportError:  # pragma: no cover
    tts_synthesize = None  # type: ignore

try:
    from voice_tracks import compute_color_offset_sec
except ImportError:  # pragma: no cover
    compute_color_offset_sec = None  # type: ignore


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
    usage_root: Path | str | None = None,
    shot_id: str = "",
    performance: dict[str, Any] | None = None,
    synthesize: Any | None = None,
) -> tuple[Path, float, dict[str, Any]]:
    """Synthesize VO via pluggable backend (fish > edge). Returns wav path, duration, meta.

    ``synthesize`` optional override for hard-compat monkeypatch of ``render_final.tts_synthesize``.
    """
    out_mp3.parent.mkdir(parents=True, exist_ok=True)
    meta: dict[str, Any] = {"backend": "edge"}
    synth = tts_synthesize if synthesize is None else synthesize
    if synth is None:
        raise RenderError("tts_backend.py missing")
    try:
        meta = synth(
            text,
            out_mp3,
            backend=backend,
            voice=voice,
            rate=rate,
            volume=volume,
            pitch=pitch,
            allow_network_fallback=allow_network_fallback,
            usage_root=usage_root,
            shot_id=shot_id,
            performance=performance,
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


def build_native_track(
    shots: list[dict[str, Any]],
    *,
    title_duration: float,
    end_duration: float,
    work: Path,
    audio_dir: Path,
    transition_sec: float = 0.0,
    join_intents: list[str] | None = None,
    sample_rate: int = SR,
) -> Path:
    """Align generated clip audio to the edited timeline, filling missing stems with silence.

    When transition_sec > 0, joins use the same acrossfade overlaps as VO/video so native
    stems stay on the xfade clock (not a hard-concat that drifts ahead of picture).
    """
    segments: list[tuple[Path | None, float, float]] = [(None, title_duration, 1.0)]
    segments.extend(
        (
            item.get("native_audio"),
            float(item["target"]),
            float(item.get("native_audio_gain", 1.0)),
        )
        for item in shots
    )
    segments.append((None, end_duration, 1.0))
    segment_durs = [float(duration) for _, duration, _ in segments]
    parts: list[Path] = []
    for index, (source, duration, gain) in enumerate(segments):
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
                    f"atrim=0:{duration:.3f},asetpts=PTS-STARTPTS,volume={gain:.4f}",
                    "-ar",
                    str(sample_rate),
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
                    f"anullsrc=r={sample_rate}:cl=stereo",
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
    default_color_gain: float = DEFAULT_VOCAL_COLOR_GAIN,
    sample_rate: int = SR,
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
        gain = float(item.get("color_gain") or default_color_gain)
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
            f"anullsrc=r={sample_rate}:cl=stereo",
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
                    f"aformat=sample_fmts=fltp:sample_rates={sample_rate}:channel_layouts=stereo,"
                    f"volume={gain:.3f},"
                    f"adelay={delay_ms}|{delay_ms},"
                    f"apad=whole_dur={max(0.05, float(total_duration)):.3f}"
                ),
                "-t",
                f"{max(0.05, float(total_duration)):.3f}",
                "-ar",
                str(sample_rate),
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
        f"aformat=sample_fmts=fltp:sample_rates={sample_rate}:channel_layouts=stereo,"
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
            str(sample_rate),
            "-ac",
            "2",
            "-c:a",
            "pcm_s16le",
            str(output),
        ]
    )
    return output

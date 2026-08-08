"""Bootstrap context for formal final (orchestrator relief W1.1).

Loads paths / film-spec / voice-mix / workspace before per-shot TTS.
Structure-only: no mix, heat, or provider policy retune.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from audio_cues import AudioCueError, primary_voice_cue
from checkpoint import CheckpointManager
from final.caption_text import flatten_shots
from final.errors import RenderError
from final.io import read_json
from final.render_helpers import resolve_render_dimension
from final.voice_mix_config import resolve_final_voice_mix_config
from logger import log
from render_workspace import RenderWorkspaceError, prepare_render_workspace, resolve_render_paths
from scene_sound import reconcile as reconcile_scene_sound
from sound_plan import validate_audio_tracks_contract


@dataclass
class RenderContext:
    """Load result for formal final; later stages still write receipts on disk."""

    root: Path
    args: Any
    paths: dict[str, Path]
    out_dir: Path
    final_path: Path
    manifest: dict[str, Any]
    spec: dict[str, Any]
    scene_sound_report: dict[str, Any]
    timeline: dict[str, Any]
    width: int
    height: int
    fps: int
    vo_mode: str
    voice: str
    cast_voices: dict[str, Any]
    vo_rate: str
    vo_pitch: str
    vo_tts_vol: str
    tts_backend: str
    tts_allow_network_fallback: bool
    cast_tts_backends: dict[str, Any]
    vo_gain: float
    voice_policy: dict[str, Any]
    native_audio_volume: float
    film_vocal_color_gain: float
    mood: str
    lipsync_mode: str
    tts_info: dict[str, Any]
    font_path: str
    shots: list[dict[str, Any]]
    shot_voice_cues: dict[str, Any]
    clips_map: dict[str, Any]
    clips_dir: Path
    audio_dir: Path
    native_dir: Path
    work: Path
    overlays_dir: Path
    checkpoint: CheckpointManager
    resume: bool
    dialogue_spoken_lang: str
    narration_spoken_lang: str
    heartbeat: Callable[[str, str | None], None] = field(repr=False)
    bgm_source_receipt: dict[str, Any] | None = None


def load_render_context(
    args: Any,
    *,
    tts_synthesize: Any,
    tts_probe: Any = None,
    resolve_font: Callable[[], str],
    enforce_dialogue_lipsync: Any = None,
    lipsync_error_cls: type[Exception] = Exception,
) -> RenderContext:
    """Resolve film root paths, gates, VO config, shots, and work dirs."""
    root = Path(args.root).expanduser().resolve()

    def _hb(stage: str, detail: str | None = None) -> None:
        try:
            from final.heartbeat import write_final_heartbeat

            write_final_heartbeat(root, stage=stage, detail=detail)
        except Exception:  # noqa: BLE001
            pass

    try:
        from final.heartbeat import apply_final_ffmpeg_timeout_env

        ff_to = apply_final_ffmpeg_timeout_env()
        _hb("start", f"render_final enter ffmpeg_timeout={ff_to}s")
    except Exception:  # noqa: BLE001
        _hb("start", "render_final enter")

    try:
        paths = resolve_render_paths(root, args.out_name)
    except RenderWorkspaceError as exc:
        raise RenderError(str(exc)) from exc
    out_dir = paths["out_dir"]
    final_path = paths["final"]
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise RenderError("ffmpeg/ffprobe required")

    if tts_synthesize is None:
        raise RenderError("tts_backend.py missing next to render_final.py")

    manifest = read_json(root / "manifest.json")
    spec = read_json(root / "film-spec.json")
    if not isinstance(manifest, dict):
        manifest = {}
    if not isinstance(spec, dict):
        raise RenderError("film-spec.json must be an object")

    scene_sound_report = reconcile_scene_sound(root, write=True)
    if bool(spec.get("audio_timeline_v1", False)) and scene_sound_report["status"] == "blocked":
        raise RenderError(
            "scene-sound required assets missing: "
            + ", ".join(scene_sound_report["blocking_shot_ids"])
        )

    audio_contract = validate_audio_tracks_contract(spec)
    for warning in audio_contract.get("warnings") or []:
        log(f"audio contract warning: {warning}")

    from production_gates import ProductionGateError, assert_no_loop_risk

    try:
        assert_no_loop_risk(root, force=bool(getattr(args, "allow_loop_risk", False)))
    except ProductionGateError as exc:
        raise RenderError(str(exc)) from exc

    timeline = read_json(root / "timeline.json") if (root / "timeline.json").is_file() else {}
    if not isinstance(timeline, dict):
        timeline = {}
    width = resolve_render_dimension(
        args.width, timeline.get("width"), manifest.get("width"), default=720
    )
    height = resolve_render_dimension(
        args.height, timeline.get("height"), manifest.get("height"), default=1280
    )
    fps = resolve_render_dimension(args.fps, timeline.get("fps"), default=30)

    _vm = resolve_final_voice_mix_config(args, spec)
    vo_mode = _vm["vo_mode"]
    voice = _vm["voice"]
    cast_voices = _vm["cast_voices"]
    vo_rate = _vm["vo_rate"]
    vo_pitch = _vm["vo_pitch"]
    vo_tts_vol = _vm["vo_tts_vol"]
    tts_backend = _vm["tts_backend"]
    tts_allow_network_fallback = _vm["tts_allow_network_fallback"]
    cast_tts_backends = _vm["cast_tts_backends"]
    vo_gain = _vm["vo_gain"]
    voice_policy = _vm["voice_policy"]
    native_audio_volume = _vm["native_audio_volume"]
    film_vocal_color_gain = _vm["film_vocal_color_gain"]
    mood = _vm["mood"]
    lipsync_mode = _vm["lipsync_mode"]
    tts_info = tts_probe() if tts_probe else {}
    log(
        f"vo_mode={vo_mode} tts={tts_backend}->{tts_info.get('active')} voice={voice} "
        f"rate={vo_rate} pitch={vo_pitch} vo_gain={vo_gain} music_vol={args.music_volume} "
        f"mood={mood} lipsync={lipsync_mode}"
    )
    font_path = resolve_font()

    shots = flatten_shots(spec, film_root=root)
    if enforce_dialogue_lipsync is None:
        if lipsync_mode != "off":
            raise RenderError(
                "post lipsync removed (v2.40); use --lipsync off and prefer_native dialogue"
            )
    else:
        try:
            lipsync_mode = enforce_dialogue_lipsync(
                vo_mode=vo_mode,
                shots=shots,
                requested=lipsync_mode,
            )
        except (lipsync_error_cls, Exception) as exc:
            raise RenderError(str(exc)) from exc
    try:
        shot_voice_cues = {str(shot["id"]): primary_voice_cue(shot) for shot in shots}
    except AudioCueError as exc:
        raise RenderError(str(exc)) from exc

    clips_map = manifest.get("clips") or {}
    try:
        prepare_render_workspace(paths)
    except RenderWorkspaceError as exc:
        raise RenderError(str(exc)) from exc
    clips_dir = paths["clips_dir"]
    audio_dir = paths["audio_dir"]
    native_dir = paths["native_dir"]
    work = paths["work"]
    overlays_dir = work / "overlays"
    checkpoint = CheckpointManager(root)
    if bool(getattr(args, "force", False)):
        checkpoint.clear()
    resume = bool(getattr(args, "resume", False))

    dialogue_spoken_lang = str(
        spec.get("dialogue_spoken_lang")
        or (spec.get("voice_policy") or {}).get("dialogue_spoken_lang")
        or "zh"
    )
    if dialogue_spoken_lang.strip().lower() in {"ja", "jp", "japanese"}:
        raise RenderError(
            "Japanese dialogue is retired; set dialogue_spoken_lang=zh (Chinese-only product)"
        )
    dialogue_spoken_lang = "zh"
    narration_spoken_lang = str(
        spec.get("narration_spoken_lang")
        or (spec.get("voice_policy") or {}).get("narration_spoken_lang")
        or "zh"
    )

    return RenderContext(
        root=root,
        args=args,
        paths=paths,
        out_dir=out_dir,
        final_path=final_path,
        manifest=manifest,
        spec=spec,
        scene_sound_report=scene_sound_report,
        timeline=timeline,
        width=width,
        height=height,
        fps=fps,
        vo_mode=vo_mode,
        voice=voice,
        cast_voices=cast_voices,
        vo_rate=vo_rate,
        vo_pitch=vo_pitch,
        vo_tts_vol=vo_tts_vol,
        tts_backend=tts_backend,
        tts_allow_network_fallback=tts_allow_network_fallback,
        cast_tts_backends=cast_tts_backends,
        vo_gain=vo_gain,
        voice_policy=voice_policy,
        native_audio_volume=native_audio_volume,
        film_vocal_color_gain=film_vocal_color_gain,
        mood=mood,
        lipsync_mode=lipsync_mode,
        tts_info=tts_info,
        font_path=font_path,
        shots=shots,
        shot_voice_cues=shot_voice_cues,
        clips_map=clips_map if isinstance(clips_map, dict) else {},
        clips_dir=clips_dir,
        audio_dir=audio_dir,
        native_dir=native_dir,
        work=work,
        overlays_dir=overlays_dir,
        checkpoint=checkpoint,
        resume=resume,
        dialogue_spoken_lang=dialogue_spoken_lang,
        narration_spoken_lang=narration_spoken_lang,
        heartbeat=_hb,
        bgm_source_receipt=None,
    )

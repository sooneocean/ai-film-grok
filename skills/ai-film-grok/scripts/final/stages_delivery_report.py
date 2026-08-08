"""Final delivery report + technical QA + technical manifest (W1.8).

After mux: write final-delivery.json, QA, longform masters, technical gate fields.
Official plate/master classification remains stages_official_finalize.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from final.errors import RenderError
from final.manifest import build_final_film_manifest_entry
from final.media_ops import pdur
from media_qa import MediaQAError, analyze_media
from security_policy import SecurityPolicyError, safe_output_path
from transition_ops import TransitionOperationError, bind_transition_operations_to_timeline
from util import utc_now, write_json


def write_technical_delivery(
    *,
    root: Path,
    out_dir: Path,
    audio_dir: Path,
    final_path: Path,
    args: Any,
    spec: dict[str, Any],
    manifest: dict[str, Any],
    film_tl: dict[str, Any],
    title_text: str,
    width: int,
    height: int,
    fps: int,
    vo_mode: str,
    voice: str,
    transition_sec: float,
    active_transition: float,
    story_intents: list[Any] | None,
    full_join_intents: list[Any],
    default_intent: str,
    xfade_plan: dict[str, Any],
    afade_plan: dict[str, Any],
    mix_spotting: dict[str, Any],
    broll_edit_report: dict[str, Any],
    broll_edit_report_sha256: str | None,
    tts_backend: str,
    cast_tts_backends: dict[str, Any],
    tts_info: dict[str, Any],
    shot_audio: list[dict[str, Any]],
    voice_cat: Path,
    music_path: Path,
    license_note: str,
    music_vol: float,
    filters_help: str,
    mood: str,
    bgm_source_receipt: dict[str, Any] | None,
    native_track: Path,
    native_audio_volume: float,
    preserved_native_shots: list[Any],
    suppressed_native_shots: list[Any],
    audio_timeline_path: Path,
    formal_timeline: dict[str, Any] | None,
    srt_path: Path,
    srt_stable: Path,
    cues: list[dict[str, Any]],
    subs_mode: str,
    lipsync_report: list[dict[str, Any]],
    sha256: Callable[[Path], str],
    timeline_caption_bindings: Callable[..., Any],
) -> dict[str, Any]:
    """Write technical delivery report + update manifest technical_final fields."""
    timeline_path = root / "timeline.json"
    mix_report_path = root / "audio" / "mix_report.json"
    try:
        bound_transition_ops = bind_transition_operations_to_timeline(
            list(spec.get("transition_ops") or []), film_timeline=film_tl
        )
    except TransitionOperationError as exc:
        raise RenderError(f"transition operation timing: {exc}") from exc
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
            "operations": bound_transition_ops,
            "film_timeline": {
                "shot_starts": film_tl.get("shot_starts"),
                "output_duration": film_tl.get("output_duration"),
                "use_ts": film_tl.get("use_ts"),
                "enabled": film_tl.get("enabled"),
                "join_intents": film_tl.get("full_join_intents") or film_tl.get("join_intents"),
            },
        },
        "sound_spotting": mix_spotting,
        "dialogue_broll": broll_edit_report,
        "dialogue_broll_report_sha256": broll_edit_report_sha256,
        "tts": {
            "backend_requested": tts_backend,
            "cast_tts_backends": cast_tts_backends,
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
            "bed_source": mix_spotting.get("bed_source"),
            "bgm_source": bgm_source_receipt,
            "honest_limits": (bgm_source_receipt or {}).get("honest_limits") or [],
        },
        "native_audio": {
            "path": str(native_track),
            "sha256": sha256(native_track),
            "volume": native_audio_volume,
            "role": mix_spotting["native_audio"]["role"],
            "ducked_under_narration": "sidechaincompress" in filters_help,
            "preserved_shots": preserved_native_shots,
            "suppressed_for_tts_shots": suppressed_native_shots,
        },
        "audio_provenance": {
            "mix_report": str(mix_report_path) if mix_report_path.is_file() else None,
            "mix_report_sha256": sha256(mix_report_path) if mix_report_path.is_file() else None,
            "audio_timeline": str(audio_timeline_path) if audio_timeline_path.is_file() else None,
            "audio_timeline_sha256": sha256(audio_timeline_path)
            if audio_timeline_path.is_file()
            else None,
            "audio_mix_execution_plan": str(audio_dir / "audio-mix-execution-plan.json")
            if formal_timeline
            else None,
        },
        "timeline": {
            "path": str(timeline_path) if timeline_path.is_file() else None,
            "sha256": sha256(timeline_path) if timeline_path.is_file() else None,
        },
        "subtitles": {
            "srt": str(srt_path),
            "srt_stable": str(srt_stable) if srt_stable != srt_path else None,
            "srt_sha256": sha256(srt_path),
            "cue_count": len(cues),
            "burned_in": subs_mode == "burn",
            "mode": subs_mode,
            "audio_event_bindings": timeline_caption_bindings(formal_timeline)
            if formal_timeline
            else None,
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
            "mode": "off",
            "frozen": True,
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
    if str(spec.get("production_mode") or "shortform") == "longform":
        from longform import LongformError, materialize_unit_masters

        try:
            report["longform_unit_masters"] = materialize_unit_masters(
                root,
                final_path=final_path,
                film_timeline=film_tl,
                shots=shot_audio,
            )
        except LongformError as exc:
            raise RenderError(f"longform unit masters: {exc}") from exc
    write_json(report_path, report)

    try:
        from timeline_clock import persist_film_timeline

        report["film_timeline_receipt"] = str(persist_film_timeline(root, film_tl))
        write_json(report_path, report)
    except Exception as tl_exc:  # noqa: BLE001
        report["film_timeline_receipt_error"] = str(tl_exc)[:160]

    # Update manifest gates (default technical final truth, overwritten after official final check).
    manifest.setdefault("outputs", {})["final_film"] = build_final_film_manifest_entry(
        final_path=final_path,
        output_sha256=report["output_sha256"],
        duration_sec=report["duration_sec"],
        report_path=report_path,
        technical_qa=technical_qa,
        official_final={"delivery_visibility": "technical_final_visible", "status": "TECHNICAL_FINAL"},
    )
    # Technical success is not human/agent end-to-end approval.
    manifest.setdefault("gates", {})["final_complete"] = False
    manifest["updated_at"] = utc_now()
    write_json(root / "manifest.json", manifest)

    return {
        "report": report,
        "report_path": report_path,
        "technical_qa": technical_qa,
        "manifest": manifest,
    }

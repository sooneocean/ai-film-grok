"""Audio / TTS / BGM / SFX / lipsync CLI cluster — extracted from aifilm_grok.

Public subcommand strings are unchanged.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from util import require_json as read_json
from util import write_json
from util.errors import FilmError
from util.subprocess import run


def _emit(obj: dict[str, Any]) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def add_audio_parsers(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    ap = sub.add_parser(
        "audio-plan", help="Dry-run audio plan; optionally compile/validate audio-timeline v1"
    )
    ap.add_argument("--root", required=True)
    ap.add_argument(
        "--compile", action="store_true", help="Include compiled audio-timeline.json data in report"
    )
    ap.add_argument(
        "--validate", action="store_true", help="Fail if the v1 audio timeline is invalid"
    )
    ap.add_argument(
        "--write-timeline",
        action="store_true",
        help="Write audio/audio-timeline.json after successful compile",
    )
    ap.add_argument(
        "--write-voice-cast",
        action="store_true",
        help="Write deterministic audio/voice-cast.json from compiled speakers",
    )
    ap.add_argument(
        "--write-tts-manifest",
        action="store_true",
        help="Write audio/tts-manifest.json with one provenance-bound job per vocal event",
    )

    av = sub.add_parser(
        "audio-verify", help="Fail closed on missing audio, TTS, or subtitle evidence"
    )
    av.add_argument("--root", required=True)
    av.add_argument("--final", default=None, help="Optional final MP4 to inspect with FFprobe")

    verify = sub.add_parser(
        "verify", help="Aggregate runtime, scene-sound, audio-delivery and production gates"
    )
    verify.add_argument("--root", required=True)
    verify.add_argument(
        "--no-write", action="store_true", help="Do not write a verification receipt"
    )

    atr = sub.add_parser(
        "audio-tts-render", help="Render each event TTS asset and write actual durations"
    )
    atr.add_argument("--root", required=True)

    aprod = sub.add_parser(
        "audio-produce",
        help="Compile TTS, BGM, Foley, and ambience into one production-audio receipt",
    )
    aprod.add_argument("--root", required=True)
    aprod.add_argument(
        "--render-tts",
        action="store_true",
        help="Render the already locked TTS jobs; does not generate BGM/Foley/ambience candidates",
    )

    ae = sub.add_parser("audio-event", help="Edit one auditable audio-timeline event")
    ae.add_argument("--root", required=True)
    ae.add_argument("--event", required=True)
    ae.add_argument("--gain", type=float, default=None)
    ae.add_argument("--pan", type=float, default=None)
    ae.add_argument("--fade-in", type=float, default=None)
    ae.add_argument("--fade-out", type=float, default=None)
    ae.add_argument("--muted", action=argparse.BooleanOptionalAction, default=None)
    ae.add_argument("--locked", action=argparse.BooleanOptionalAction, default=None)
    ae.add_argument("--overlap-policy", choices=("interrupt", "cross_talk"), default=None)
    ae.add_argument("--text", default=None)
    ae.add_argument("--caption-text", default=None)
    ae.add_argument("--performance-json", default=None)
    ae.add_argument("--force-locked", action="store_true")

    bgm_candidate = sub.add_parser(
        "bgm-candidate",
        help="Generate ACE-Step BGM candidates, then explicitly approve them into the local pool",
    )
    bgm_candidate_sub = bgm_candidate.add_subparsers(dest="bgm_candidate_action", required=True)
    bgm_generate = bgm_candidate_sub.add_parser("generate", help="Create one pending BGM candidate")
    bgm_generate.add_argument("--root", required=True)
    bgm_generate.add_argument("--prompt", default="")
    bgm_generate.add_argument("--mood", default="rnb")
    bgm_generate.add_argument("--duration", type=float, default=30.0)
    bgm_generate.add_argument("--seed", type=int, required=True)
    bgm_list = bgm_candidate_sub.add_parser("list", help="List pending and approved BGM candidates")
    bgm_list.add_argument("--root", required=True)
    bgm_approve = bgm_candidate_sub.add_parser(
        "approve", help="Promote one heard candidate to audio/templates/<mood>/"
    )
    bgm_approve.add_argument("--root", required=True)
    bgm_approve.add_argument("--asset-id", required=True)
    bgm_approve.add_argument("--target", choices=("film", "shared"), default="film")
    bgm_approve.add_argument("--reviewer", default="")
    bgm_approve.add_argument("--license-note", default="")
    bgm_approve.add_argument("--instrumental-confirmed", action="store_true")

    performance_candidate = sub.add_parser(
        "performance-candidate",
        help="Generate private non-verbal performance candidates with explicit adult and source authorization",
    )
    performance_candidate_sub = performance_candidate.add_subparsers(
        dest="performance_candidate_action", required=True
    )
    performance_generate = performance_candidate_sub.add_parser(
        "generate", help="Create one pending performance candidate"
    )
    performance_generate.add_argument("--root", required=True)
    performance_generate.add_argument("--cue", required=True)
    performance_generate.add_argument("--duration", type=float, default=3.0)
    performance_generate.add_argument("--seed", type=int, required=True)
    performance_generate.add_argument("--character-id", required=True)
    performance_generate.add_argument(
        "--source-authorization", choices=("original", "authorized_reference"), required=True
    )
    performance_generate.add_argument("--adult-confirmed", action="store_true")
    performance_generate.add_argument("--model-version", default="higgs-audio-v2")
    performance_approve = performance_candidate_sub.add_parser(
        "approve", help="Promote one human-heard performance candidate"
    )
    performance_approve.add_argument("--root", required=True)
    performance_approve.add_argument("--asset-id", required=True)
    performance_reject = performance_candidate_sub.add_parser(
        "reject", help="Record a human rejection; rejected candidates cannot be approved"
    )
    performance_reject.add_argument("--root", required=True)
    performance_reject.add_argument("--asset-id", required=True)
    performance_reject.add_argument("--reviewer", required=True)
    performance_reject.add_argument("--reason", required=True)

    adult_female_voice_pack = sub.add_parser(
        "adult-female-voice-pack",
        help="Create, render, review, and approve fixed-profile adult female dialogue/breath candidates",
    )
    adult_female_voice_pack_sub = adult_female_voice_pack.add_subparsers(
        dest="adult_female_voice_pack_action", required=True
    )
    adult_female_voice_pack_init = adult_female_voice_pack_sub.add_parser("init")
    adult_female_voice_pack_init.add_argument("--root", required=True)
    adult_female_voice_pack_render = adult_female_voice_pack_sub.add_parser("render")
    adult_female_voice_pack_render.add_argument("--root", required=True)
    adult_female_voice_pack_render.add_argument(
        "--node-url",
        default="",
        help="Optional private LAN or Tailscale 100.x audio-node URL; does not persist config",
    )
    adult_female_voice_pack_list = adult_female_voice_pack_sub.add_parser("list")
    adult_female_voice_pack_list.add_argument("--root", required=True)
    adult_female_voice_pack_approve = adult_female_voice_pack_sub.add_parser("approve")
    adult_female_voice_pack_approve.add_argument("--root", required=True)
    adult_female_voice_pack_approve.add_argument("--asset-id", required=True)
    adult_female_voice_pack_approve.add_argument("--reviewer", required=True)
    adult_female_voice_pack_approve.add_argument("--female-voice-confirmed", action="store_true")
    adult_female_voice_pack_approve.add_argument("--breath-confirmed", action="store_true")
    adult_female_voice_pack_approve.add_argument("--artifact-free-confirmed", action="store_true")

    ambience_candidate = sub.add_parser(
        "ambience-candidate", help="Generate and human-approve Stable Audio ambience candidates"
    )
    ambience_sub = ambience_candidate.add_subparsers(
        dest="ambience_candidate_action", required=True
    )
    ambience_generate = ambience_sub.add_parser("generate")
    ambience_generate.add_argument("--root", required=True)
    ambience_generate.add_argument("--prompt", required=True)
    ambience_generate.add_argument("--duration", type=float, default=10.0)
    ambience_generate.add_argument("--seed", type=int, required=True)
    ambience_list = ambience_sub.add_parser("list")
    ambience_list.add_argument("--root", required=True)
    ambience_approve = ambience_sub.add_parser("approve")
    ambience_approve.add_argument("--root", required=True)
    ambience_approve.add_argument("--asset-id", required=True)
    ambience_approve.add_argument("--reviewer", required=True)
    ambience_approve.add_argument("--heard-full", action="store_true")
    ambience_approve.add_argument("--no-speech-confirmed", action="store_true")
    ambience_approve.add_argument("--no-music-confirmed", action="store_true")
    ambience_approve.add_argument("--artifact-free-confirmed", action="store_true")
    ambience_attach = ambience_sub.add_parser("attach")
    ambience_attach.add_argument("--root", required=True)
    ambience_attach.add_argument("--asset-id", required=True)
    ambience_attach.add_argument("--shot-id", required=True)
    ambience_attach.add_argument("--start-offset-sec", type=float, required=True)
    ambience_attach.add_argument("--duration", type=float, required=True)
    ambience_attach.add_argument("--acoustic-space", required=True)
    ambience_attach.add_argument("--noncommercial-internal-ok", action="store_true")

    sfx_canary = sub.add_parser(
        "sfx-canary",
        help="Generate one pending, non-commercial MMAudio SFX pilot on the private RTX node",
    )
    sfx_canary.add_argument("--root", required=True)
    sfx_canary.add_argument("--prompt", required=True)
    sfx_canary.add_argument("--duration", type=float, default=8.0)
    sfx_canary.add_argument("--seed", type=int, required=True)
    sfx_canary.add_argument("--video", default="")
    sfx_canary.add_argument("--noncommercial-research-ok", action="store_true")

    sfx_candidate = sub.add_parser(
        "sfx-candidate",
        help="Generate, human-review, and attach internal non-commercial MMAudio SFX",
    )
    sfx_candidate_sub = sfx_candidate.add_subparsers(dest="sfx_candidate_action", required=True)
    sfx_generate = sfx_candidate_sub.add_parser("generate")
    sfx_generate.add_argument("--root", required=True)
    sfx_generate.add_argument("--prompt", required=True)
    sfx_generate.add_argument("--duration", type=float, default=8.0)
    sfx_generate.add_argument("--seed", type=int, required=True)
    sfx_generate.add_argument("--video", default="")
    sfx_generate.add_argument("--noncommercial-research-ok", action="store_true")
    sfx_batch = sfx_candidate_sub.add_parser(
        "batch", help="Generate and ASR-screen 1-24 non-commercial SFX candidates"
    )
    sfx_batch.add_argument("--root", required=True)
    sfx_batch.add_argument(
        "--manifest", required=True, help="JSON: {candidates:[{prompt,duration,seed}]}"
    )
    sfx_batch.add_argument("--noncommercial-research-ok", action="store_true")
    sfx_approve = sfx_candidate_sub.add_parser("approve")
    sfx_approve.add_argument("--root", required=True)
    sfx_approve.add_argument("--asset-id", required=True)
    sfx_approve.add_argument("--reviewer", required=True)
    sfx_approve.add_argument("--heard-full", action="store_true")
    sfx_approve.add_argument("--sync-confirmed", action="store_true")
    sfx_approve.add_argument("--no-speech-confirmed", action="store_true")
    sfx_approve.add_argument("--no-music-confirmed", action="store_true")
    sfx_approve.add_argument("--artifact-free-confirmed", action="store_true")
    sfx_approve.add_argument(
        "--asr-speech-reviewed",
        action="store_true",
        help="Confirm that the candidate-only ASR leakage signal was reviewed; human listening remains required",
    )
    sfx_screen = sfx_candidate_sub.add_parser(
        "screen-speech",
        help="Run candidate-only VibeVoice-ASR leakage screening before human SFX approval",
    )
    sfx_screen.add_argument("--root", required=True)
    sfx_screen.add_argument("--asset-id", required=True)
    sfx_reject = sfx_candidate_sub.add_parser("reject")
    sfx_reject.add_argument("--root", required=True)
    sfx_reject.add_argument("--asset-id", required=True)
    sfx_reject.add_argument("--reviewer", required=True)
    sfx_reject.add_argument("--reason", required=True)
    sfx_attach = sfx_candidate_sub.add_parser("attach")
    sfx_attach.add_argument("--root", required=True)
    sfx_attach.add_argument("--asset-id", required=True)
    sfx_attach.add_argument("--shot-id", required=True)
    sfx_attach.add_argument("--kind", choices=("foley", "sfx"), required=True)
    sfx_attach.add_argument("--start-offset-sec", type=float, required=True)
    sfx_attach.add_argument("--duration", type=float, required=True)
    sfx_attach.add_argument("--material", required=True)
    sfx_attach.add_argument("--noncommercial-internal-ok", action="store_true")

    sfx_library = sub.add_parser(
        "sfx-library",
        help="Audit or import signed MMAudio takes into the shared non-commercial SFX armory",
    )
    sfx_library_sub = sfx_library.add_subparsers(dest="sfx_library_action", required=True)
    sfx_library_audit = sfx_library_sub.add_parser("audit")
    sfx_library_audit.add_argument("--library-root", default="")
    sfx_library_import = sfx_library_sub.add_parser("import-project")
    sfx_library_import.add_argument("--root", required=True, help="Legacy film project root")
    sfx_library_import.add_argument("--asset-id", required=True)
    sfx_library_import.add_argument("--library-root", default="")
    sfx_library_review = sfx_library_sub.add_parser(
        "review-pack", help="Write a listening pack from retained global SFX candidates"
    )
    sfx_library_review.add_argument("--name", required=True)
    sfx_library_review.add_argument("--library-root", default="")

    lsc = sub.add_parser(
        "lipsync-canary",
        help="Single-shot lipsync probe → receipts/lipsync-canary/ (default final still lipsync off)",
    )
    lsc.add_argument("--root", required=True)
    lsc.add_argument("--shot", "--shot-id", dest="shot_id", required=True)
    lsc.add_argument("--backend", default="auto")
    lsc.add_argument("--video", default=None)
    lsc.add_argument("--audio", default=None)

    lsp = sub.add_parser(
        "lipsync-pilot",
        help="Three-shot close-dialogue LatentSync pilot; never promotes candidate media",
    )
    lsp_sub = lsp.add_subparsers(dest="lipsync_pilot_action", required=True)
    lsp_create = lsp_sub.add_parser(
        "create", help="Register three distinct standard samples and one Japanese dialogue track"
    )
    lsp_create.add_argument("--root", required=True)
    lsp_create.add_argument("--front-video", required=True)
    lsp_create.add_argument("--three-quarter-video", required=True)
    lsp_create.add_argument("--moving-video", required=True)
    lsp_create.add_argument("--japanese-audio", required=True)
    lsp_create.add_argument("--approval-receipt", required=True)
    lsp_run = lsp_sub.add_parser(
        "run", help="Run only after the shared ComfyUI queue is proved empty"
    )
    lsp_run.add_argument("--root", required=True)
    lsp_muse = lsp_sub.add_parser(
        "rerun-musetalk",
        help="Explicit manual fallback after a classified LatentSync technical failure",
    )
    lsp_muse.add_argument("--root", required=True)
    lsp_muse.add_argument(
        "--sample",
        required=True,
        choices=("front_closeup", "three_quarter_closeup", "moving_closeup"),
    )
    lsp_review = lsp_sub.add_parser(
        "review-template", help="Write a human review template for completed pilot outputs"
    )
    lsp_review.add_argument("--root", required=True)

    lsch = sub.add_parser(
        "lipsync-challenge",
        help="Plan and evaluate the four-backend lip-sync challenge without running GPU work",
    )
    lsch_sub = lsch.add_subparsers(dest="lipsync_challenge_action", required=True)
    lsch_create = lsch_sub.add_parser("create")
    lsch_create.add_argument("--root", required=True)
    lsch_create.add_argument("--front-closeup", required=True)
    lsch_create.add_argument("--three-quarter", required=True)
    lsch_create.add_argument("--occlusion-motion", required=True)
    lsch_create.add_argument("--anime", required=True)
    lsch_create.add_argument("--japanese-audio", required=True)
    lsch_create.add_argument("--approval-receipt", required=True)
    lsch_register = lsch_sub.add_parser("register-result")
    lsch_register.add_argument("--root", required=True)
    lsch_register.add_argument(
        "--fixture-id",
        required=True,
        choices=("front_closeup", "three_quarter", "occlusion_motion", "anime"),
    )
    lsch_register.add_argument(
        "--backend-id",
        required=True,
        choices=(
            "latentsync-1.6",
            "echomimic-v3-flash",
            "longcat-video-avatar-1.5",
        ),
    )
    lsch_register.add_argument("--output", required=True)
    lsch_register.add_argument("--metrics-receipt", required=True)
    lsch_register.add_argument("--runtime-receipt", required=True)
    lsch_package = lsch_sub.add_parser("blind-package")
    lsch_package.add_argument("--root", required=True)
    lsch_review = lsch_sub.add_parser("review")
    lsch_review.add_argument("--root", required=True)
    lsch_review.add_argument("--reviewer", required=True)
    lsch_review.add_argument("--review-json", required=True)
    lsch_report = lsch_sub.add_parser("report")
    lsch_report.add_argument("--root", required=True)
    lsch_report.add_argument("--license-receipt", default="")

    lsn = sub.add_parser(
        "lipsync-node",
        help="Inspect the authenticated Windows RTX lip-sync node",
    )
    lsn.add_argument(
        "lipsync_node_action",
        nargs="?",
        default="health",
        choices=["health"],
    )

    cap = sub.add_parser(
        "capability",
        help="One-page readiness (TTS/BGM/lipsync/tools + optional FRW canary / i2v suggest)",
    )
    cap.add_argument(
        "--root", default=None, help="Film root (reads frw canary receipt + film-spec)"
    )
    cap.add_argument(
        "--run-canary",
        action="store_true",
        help="Hit FRW API canary and write receipts/frw-key-capability.json (costs credits)",
    )
    cap.add_argument("--canary-wait", action="store_true", help="With --run-canary: poll ltx-t2v")
    cap.add_argument(
        "--canary-full", action="store_true", help="With --run-canary: full template probes"
    )
    cap.add_argument(
        "--suggest-i2v",
        action="store_true",
        help="From canary receipt, suggest i2v_provider / frw_* patch (no write unless --apply)",
    )
    cap.add_argument(
        "--apply",
        action="store_true",
        help="Opt-in: write suggested i2v fields into film-spec.json (then re-run write-spec)",
    )

    tab = sub.add_parser(
        "tts-ab",
        help="A/B TTS same nar through multiple backends → receipts/tts-ab/ (no film-spec change)",
    )
    tab.add_argument("--root", required=True)
    tab.add_argument("--shot", "--shot-id", dest="shot_id", required=True)
    tab.add_argument(
        "--backends",
        default="mimo,edge",
        help="Comma-separated backends (default: mimo,edge)",
    )
    tab.add_argument("--voice", default=None)
    tab.add_argument("--text", default=None, help="Override shot nar")
    tab.add_argument("--spec", default=None)

    el_canary = sub.add_parser(
        "elevenlabs-canary",
        help="Bounded Chinese+Japanese ElevenLabs TTS canary; candidates need human review",
    )
    el_canary.add_argument("--root", required=True)
    el_canary.add_argument("--zh-voice", default="", help="ElevenLabs provider voice ID")
    el_canary.add_argument("--ja-voice", default="", help="ElevenLabs provider voice ID")
    el_canary.add_argument("--model", default="eleven_multilingual_v2")
    el_canary.add_argument("--confirm-cost", action="store_true")
    el_canary.add_argument("--max-paid-calls", type=int, default=0)
    el_canary.add_argument(
        "--list-voices", action="store_true", help="List account voices; no synthesis"
    )
    el_canary.add_argument("--review-language", choices=("zh", "ja"))
    el_canary.add_argument("--decision", choices=("approve", "reject"))

    treh = sub.add_parser(
        "tts-rehearse",
        help="Probe/register real VO durations into receipts/tts-rehearsal.json before bulk/final",
    )
    treh.add_argument("--root", required=True)
    treh.add_argument("--spec", default=None, help="Optional film-spec path")
    treh.add_argument("--backend", "--tts-backend", dest="tts_backend", default=None)
    treh.add_argument("--voice", default="zh-CN-XiaoxiaoNeural")
    treh.add_argument(
        "--register-json",
        default=None,
        help="JSON list of {shot_id, path|measured_duration_sec} (offline / no network)",
    )
    treh.add_argument(
        "--no-synthesize",
        action="store_true",
        help="Only register mode; requires --register-json",
    )


def cmd_audio_plan(args: argparse.Namespace) -> int:
    from audio_plan import build_audio_plan

    root = Path(args.root).expanduser().resolve()
    report = build_audio_plan(
        root,
        compile_timeline=bool(getattr(args, "compile", False) or getattr(args, "validate", False)),
        write_timeline=bool(getattr(args, "write_timeline", False)),
        write_voice_cast=bool(getattr(args, "write_voice_cast", False)),
        write_tts_manifest=bool(getattr(args, "write_tts_manifest", False)),
    )
    _emit(report)
    return (
        1 if bool(getattr(args, "validate", False)) and report["audio_timeline"].get("error") else 0
    )


def cmd_audio_verify(args: argparse.Namespace) -> int:
    """Run the fail-closed audio delivery evidence gate for one film root."""
    from audio_delivery_gate import build_delivery_report
    from util import read_json, write_json

    root = Path(args.root).expanduser().resolve()
    audio_dir = root / "audio"
    timeline = read_json(audio_dir / "audio-timeline.json")
    manifest = read_json(audio_dir / "tts-manifest.json")
    bindings = read_json(audio_dir / "caption-bindings.json")
    production = read_json(audio_dir / "production-plan.json")
    scene_sound = read_json(root / "receipts" / "scene-sound-status.json")
    if (
        not isinstance(timeline, dict)
        or not isinstance(manifest, dict)
        or not isinstance(bindings, list)
        or not isinstance(production, dict)
        or not isinstance(scene_sound, dict)
    ):
        raise FilmError(
            "audio-verify requires unified production artifacts; run audio-produce first"
        )
    final_path = Path(args.final).expanduser().resolve() if args.final else None
    out = audio_dir / "audio-delivery-report.json"
    previous_report = read_json(out) if out.is_file() else None
    report = build_delivery_report(
        timeline=timeline,
        tts_manifest=manifest,
        subtitle_bindings=bindings,
        final_mp4=final_path,
        previous_report=previous_report if isinstance(previous_report, dict) else None,
        root=root,
        audio_production=production,
        scene_sound_receipt=scene_sound,
    )
    write_json(out, report)
    _emit({**report, "path": str(out)})
    return 0 if report["ok"] else 1


def cmd_verify(args: argparse.Namespace) -> int:
    """Aggregate local automation gates without initiating generation or uploads."""
    from automation_verify import build_verification_report
    from util import write_json

    root = Path(args.root).expanduser().resolve()
    report = build_verification_report(root)
    if not bool(getattr(args, "no_write", False)):
        out = root / "receipts" / "automation-verify.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        write_json(out, report)
        report["path"] = str(out)
    _emit(report)
    return 0 if report["ok"] else 1


def cmd_audio_tts_render(args: argparse.Namespace) -> int:
    from audio_tts_render import AudioTTSRenderError, render_tts_events

    try:
        _emit(render_tts_events(Path(args.root)))
    except AudioTTSRenderError as exc:
        raise FilmError(str(exc)) from exc
    return 0


def cmd_audio_produce(args: argparse.Namespace) -> int:
    """Prepare the unified production-audio contract for one film."""
    from audio_production import AudioProductionError, prepare_audio_production

    try:
        _emit(prepare_audio_production(Path(args.root), render_tts=bool(args.render_tts)))
    except AudioProductionError as exc:
        raise FilmError(str(exc)) from exc
    return 0


def cmd_audio_event(args: argparse.Namespace) -> int:
    from audio_event_editor import AudioEventEditError, edit_event
    from util import read_json, write_json

    root = Path(args.root).expanduser().resolve()
    audio_dir = root / "audio"
    timeline = read_json(audio_dir / "audio-timeline.json")
    if not isinstance(timeline, dict):
        raise FilmError("audio-event requires audio/audio-timeline.json")
    updates = {
        key: value
        for key, value in {
            "gain": args.gain,
            "pan": args.pan,
            "fade_in_sec": args.fade_in,
            "fade_out_sec": args.fade_out,
            "muted": args.muted,
            "locked": args.locked,
            "overlap_policy": args.overlap_policy,
            "text": args.text,
            "caption_text": args.caption_text,
        }.items()
        if value is not None
    }
    if args.performance_json is not None:
        try:
            updates["performance_cue"] = json.loads(args.performance_json)
        except json.JSONDecodeError as exc:
            raise FilmError("--performance-json must be valid JSON") from exc
    if not updates:
        raise FilmError("audio-event needs at least one control update")
    manifest_path = audio_dir / "tts-manifest.json"
    manifest = read_json(manifest_path) if manifest_path.is_file() else None
    try:
        edited, updated_manifest, bindings = edit_event(
            timeline,
            args.event,
            updates,
            force_locked=bool(args.force_locked),
            tts_manifest=manifest,
        )
    except AudioEventEditError as exc:
        raise FilmError(str(exc)) from exc
    write_json(audio_dir / "audio-timeline.json", edited)
    write_json(audio_dir / "caption-bindings.json", bindings)
    if updated_manifest is not None:
        write_json(manifest_path, updated_manifest)
    _emit({"ok": True, "audio_event_id": args.event, "updates": updates})
    return 0


def cmd_bgm_candidate(args: argparse.Namespace) -> int:
    """Create/list/approve locally rendered ACE-Step BGM candidates."""
    from bgm_candidates import BGMCandidateError, approve, generate, list_candidates

    root = Path(args.root).expanduser().resolve()
    try:
        if args.bgm_candidate_action == "list":
            _emit({"candidates": list_candidates(root)})
            return 0
        if args.bgm_candidate_action == "approve":
            if str(getattr(args, "target", "film") or "film") == "shared":
                from bgm_library import approve_candidate as approve_shared
                from bgm_library import default_library_root, stage_candidate

                candidates = {
                    str(item.get("asset_id") or ""): item for item in list_candidates(root)
                }
                source_record = candidates.get(str(args.asset_id))
                if not isinstance(source_record, dict):
                    raise BGMCandidateError("BGM candidate receipt not found")
                source = root / str(source_record.get("path") or "")
                staged = stage_candidate(
                    default_library_root(),
                    source,
                    {
                        "mood": source_record.get("mood") or "rnb",
                        "seed": source_record.get("seed") or 0,
                        "model": source_record.get("model") or "ACE-Step-1.5",
                        "checkpoint_fingerprint": source_record.get("checkpoint_fingerprint")
                        or "unknown",
                        "node_job_id": source_record.get("node_job_id") or "",
                        "prompt_sha256": source_record.get("prompt_sha256") or "",
                        "dramatic_tags": [],
                        "energy": 0.5,
                        "stem_profile": "pad",
                        "recipe": {
                            "mood": source_record.get("mood") or "rnb",
                            "energy": 0.5,
                            "stem_profile": "pad",
                        },
                    },
                )
                _emit(
                    approve_shared(
                        default_library_root(),
                        str(staged["asset_id"]),
                        reviewer=str(getattr(args, "reviewer", "") or ""),
                        license_note=str(getattr(args, "license_note", "") or ""),
                        instrumental_confirmed=bool(getattr(args, "instrumental_confirmed", False)),
                    )
                )
                return 0
            _emit(approve(root, args.asset_id))
            return 0
        base = os.environ.get("AIFILM_AUDIO_NODE_URL", "").strip()
        token = os.environ.get("AIFILM_AUDIO_NODE_TOKEN", "").strip()
        if not base or not token:
            raise BGMCandidateError("AIFILM_AUDIO_NODE_URL/TOKEN are required for ACE-Step BGM")
        prompt = (args.prompt or "").strip() or (
            f"instrumental {args.mood} background music, cinematic underscore, no vocals"
        )
        _emit(
            generate(
                root,
                base_url=base,
                token=token,
                prompt=prompt,
                mood=args.mood,
                duration=args.duration,
                seed=args.seed,
            )
        )
        return 0
    except BGMCandidateError as exc:
        raise FilmError(str(exc)) from exc


def cmd_bgm_library(args: argparse.Namespace) -> int:
    from bgm_library import BGMLibraryError
    from cli_bgm_library import cmd_bgm_library as run_bgm_library

    try:
        return run_bgm_library(args, emit=emit)
    except BGMLibraryError as exc:
        raise FilmError(str(exc)) from exc


def cmd_performance_candidate(args: argparse.Namespace) -> int:
    """Create, reject, or approve private non-verbal performance candidates."""
    from config_loader import get_config
    from performance_candidates import PerformanceCandidateError, approve, generate, reject

    get_config()
    root = Path(args.root).expanduser().resolve()
    try:
        if args.performance_candidate_action == "approve":
            _emit(approve(root, args.asset_id))
            return 0
        if args.performance_candidate_action == "reject":
            _emit(reject(root, args.asset_id, reviewer=args.reviewer, reason=args.reason))
            return 0
        base = os.environ.get("AIFILM_AUDIO_NODE_URL", "").strip()
        token = os.environ.get("AIFILM_AUDIO_NODE_TOKEN", "").strip()
        if not base or not token:
            raise PerformanceCandidateError(
                "AIFILM_AUDIO_NODE_URL/TOKEN are required for performance generation"
            )
        _emit(
            generate(
                root,
                base_url=base,
                token=token,
                cue=args.cue,
                duration=args.duration,
                seed=args.seed,
                character_id=args.character_id,
                source_authorization=args.source_authorization,
                adult_confirmed=bool(args.adult_confirmed),
                model_version=args.model_version,
            )
        )
        return 0
    except PerformanceCandidateError as exc:
        raise FilmError(str(exc)) from exc


def cmd_adult_female_voice_pack(args: argparse.Namespace) -> int:
    """Manage fixed-profile, human-reviewed adult female dialogue and breath candidates."""
    from adult_female_voice_pack import (
        AdultFemaleVoicePackError,
        approve,
        initialize,
        list_candidates,
        render_pending,
    )
    from config_loader import get_config

    get_config()
    root = Path(args.root).expanduser().resolve()
    try:
        if args.adult_female_voice_pack_action == "init":
            _emit(initialize(root))
            return 0
        if args.adult_female_voice_pack_action == "list":
            _emit({"candidates": list_candidates(root)})
            return 0
        if args.adult_female_voice_pack_action == "approve":
            _emit(
                approve(
                    root,
                    args.asset_id,
                    reviewer=args.reviewer,
                    female_voice_confirmed=bool(args.female_voice_confirmed),
                    breath_confirmed=bool(args.breath_confirmed),
                    artifact_free_confirmed=bool(args.artifact_free_confirmed),
                )
            )
            return 0
        base = str(
            getattr(args, "node_url", "") or os.environ.get("AIFILM_AUDIO_NODE_URL", "")
        ).strip()
        token = os.environ.get("AIFILM_AUDIO_NODE_TOKEN", "").strip()
        if not base or not token:
            raise AdultFemaleVoicePackError("AIFILM_AUDIO_NODE_URL/TOKEN are required")
        _emit(render_pending(root, base_url=base, token=token))
        return 0
    except AdultFemaleVoicePackError as exc:
        raise FilmError(str(exc)) from exc


def cmd_ambience_candidate(args: argparse.Namespace) -> int:
    from ambience_candidates import (
        AmbienceCandidateError,
        approve,
        attach_to_shot,
        generate,
        list_candidates,
    )

    root = Path(args.root).expanduser().resolve()
    try:
        if args.ambience_candidate_action == "list":
            _emit({"candidates": list_candidates(root)})
        elif args.ambience_candidate_action == "approve":
            _emit(
                approve(
                    root,
                    args.asset_id,
                    reviewer=args.reviewer,
                    heard_full=bool(args.heard_full),
                    no_speech_confirmed=bool(args.no_speech_confirmed),
                    no_music_confirmed=bool(args.no_music_confirmed),
                    artifact_free_confirmed=bool(args.artifact_free_confirmed),
                )
            )
        elif args.ambience_candidate_action == "attach":
            _emit(
                attach_to_shot(
                    root,
                    args.asset_id,
                    shot_id=args.shot_id,
                    start_offset_sec=args.start_offset_sec,
                    duration_sec=args.duration,
                    acoustic_space=args.acoustic_space,
                    noncommercial_internal_ok=bool(args.noncommercial_internal_ok),
                )
            )
        else:
            base, token = (
                os.environ.get("AIFILM_AUDIO_NODE_URL", ""),
                os.environ.get("AIFILM_AUDIO_NODE_TOKEN", ""),
            )
            if not base or not token:
                raise AmbienceCandidateError("AIFILM_AUDIO_NODE_URL/TOKEN are required")
            _emit(
                generate(
                    root,
                    base_url=base,
                    token=token,
                    prompt=args.prompt,
                    duration=args.duration,
                    seed=args.seed,
                )
            )
        return 0
    except AmbienceCandidateError as exc:
        raise FilmError(str(exc)) from exc


def cmd_sfx_canary(args: argparse.Namespace) -> int:
    """Generate one non-commercial, pending MMAudio SFX candidate."""
    from sfx_candidates import SFXCandidateError, generate

    try:
        _emit(
            generate(
                Path(args.root),
                prompt=args.prompt,
                duration=args.duration,
                seed=args.seed,
                source_video=Path(args.video).expanduser() if args.video else None,
                noncommercial_research_ok=bool(args.noncommercial_research_ok),
            )
        )
        return 0
    except SFXCandidateError as exc:
        raise FilmError(str(exc)) from exc


def cmd_sfx_candidate(args: argparse.Namespace) -> int:
    """Generate, review, and attach non-commercial MMAudio SFX."""
    # Candidate receipts are HMAC-bound to the local audio-node credential.
    # Generation loads config itself, but the later review subcommands must
    # load the same local-only configuration before verifying that signature.
    from config_loader import get_config
    from sfx_candidates import (
        SFXCandidateError,
        approve,
        attach_to_shot,
        batch_generate_and_screen,
        generate,
        reject,
        screen_speech,
    )

    get_config()
    root = Path(args.root).expanduser().resolve()
    try:
        if args.sfx_candidate_action == "batch":
            payload = read_json(Path(args.manifest))
            candidates = payload.get("candidates") if isinstance(payload, dict) else None
            if not isinstance(candidates, list):
                raise SFXCandidateError("SFX batch manifest requires candidates array")
            _emit(
                batch_generate_and_screen(
                    root,
                    candidates,
                    noncommercial_research_ok=bool(args.noncommercial_research_ok),
                )
            )
        elif args.sfx_candidate_action == "approve":
            _emit(
                approve(
                    root,
                    args.asset_id,
                    reviewer=args.reviewer,
                    heard_full=bool(args.heard_full),
                    sync_confirmed=bool(args.sync_confirmed),
                    no_speech_confirmed=bool(args.no_speech_confirmed),
                    no_music_confirmed=bool(args.no_music_confirmed),
                    artifact_free_confirmed=bool(args.artifact_free_confirmed),
                    asr_speech_reviewed=bool(args.asr_speech_reviewed),
                )
            )
        elif args.sfx_candidate_action == "screen-speech":
            _emit(screen_speech(root, args.asset_id))
        elif args.sfx_candidate_action == "reject":
            _emit(
                reject(
                    root,
                    args.asset_id,
                    reviewer=args.reviewer,
                    reason=args.reason,
                )
            )
        elif args.sfx_candidate_action == "attach":
            _emit(
                attach_to_shot(
                    root,
                    args.asset_id,
                    shot_id=args.shot_id,
                    kind=args.kind,
                    start_offset_sec=args.start_offset_sec,
                    duration_sec=args.duration,
                    material=args.material,
                    noncommercial_internal_ok=bool(args.noncommercial_internal_ok),
                )
            )
        else:
            _emit(
                generate(
                    root,
                    prompt=args.prompt,
                    duration=args.duration,
                    seed=args.seed,
                    source_video=Path(args.video).expanduser() if args.video else None,
                    noncommercial_research_ok=bool(args.noncommercial_research_ok),
                )
            )
        return 0
    except SFXCandidateError as exc:
        raise FilmError(str(exc)) from exc


def cmd_sfx_library(args: argparse.Namespace) -> int:
    """Manage the shared internal non-commercial SFX armory."""
    from config_loader import get_config
    from sfx_library import (
        SFXLibraryError,
        audit,
        import_project_asset,
        write_candidate_review_pack,
    )

    get_config()
    try:
        if args.sfx_library_action == "import-project":
            _emit(
                import_project_asset(
                    Path(args.root),
                    args.asset_id,
                    library_root=Path(args.library_root) if args.library_root else None,
                )
            )
        elif args.sfx_library_action == "review-pack":
            _emit(
                write_candidate_review_pack(
                    args.name,
                    library_root=Path(args.library_root) if args.library_root else None,
                )
            )
        else:
            _emit(audit(library_root=Path(args.library_root) if args.library_root else None))
        return 0
    except SFXLibraryError as exc:
        raise FilmError(str(exc)) from exc


def cmd_lipsync_canary(args: argparse.Namespace) -> int:
    from lipsync_canary import LipsyncCanaryError, run_lipsync_canary

    root = Path(args.root).expanduser().resolve()
    try:
        report = run_lipsync_canary(
            root,
            shot_id=str(args.shot_id),
            backend=str(getattr(args, "backend", None) or "auto"),
            video=Path(args.video).expanduser() if getattr(args, "video", None) else None,
            audio=Path(args.audio).expanduser() if getattr(args, "audio", None) else None,
        )
    except LipsyncCanaryError as exc:
        raise FilmError(str(exc)) from exc
    _emit(report)
    # not ready unlock path is soft fail (exit 1) but not crash
    return 0 if report.get("ok") else 1


def cmd_lipsync_pilot(args: argparse.Namespace) -> int:
    from lipsync_pilot import (
        LipsyncPilotError,
        create_pilot,
        rerun_musetalk,
        review_template,
        run_pilot,
    )

    try:
        action = str(args.lipsync_pilot_action)
        if action == "create":
            report = create_pilot(
                args.root,
                front_video=args.front_video,
                three_quarter_video=args.three_quarter_video,
                moving_video=args.moving_video,
                japanese_audio=args.japanese_audio,
                approval_receipt=args.approval_receipt,
            )
        elif action == "run":
            report = run_pilot(args.root)
        elif action == "rerun-musetalk":
            report = rerun_musetalk(args.root, sample_id=args.sample)
        else:
            report = review_template(args.root)
    except LipsyncPilotError as exc:
        raise FilmError(str(exc)) from exc
    _emit(report)
    return 0 if report.get("ok", True) else 1


def cmd_lipsync_challenge(args: argparse.Namespace) -> int:
    from lipsync_challenge import (
        LipsyncChallengeError,
        build_challenge_report,
        create_blind_package,
        create_challenge,
        record_blind_review,
        register_result,
    )

    try:
        action = str(args.lipsync_challenge_action)
        if action == "create":
            report = create_challenge(
                args.root,
                fixtures={
                    "front_closeup": Path(args.front_closeup),
                    "three_quarter": Path(args.three_quarter),
                    "occlusion_motion": Path(args.occlusion_motion),
                    "anime": Path(args.anime),
                },
                japanese_audio=Path(args.japanese_audio),
                approval_receipt=Path(args.approval_receipt),
            )
        elif action == "register-result":
            report = register_result(
                args.root,
                fixture_id=args.fixture_id,
                backend_id=args.backend_id,
                output=Path(args.output),
                metrics_receipt=Path(args.metrics_receipt),
                runtime_receipt=Path(args.runtime_receipt),
            )
        elif action == "blind-package":
            report = create_blind_package(args.root)
        elif action == "review":
            report = record_blind_review(
                args.root,
                reviewer=args.reviewer,
                review=read_json(Path(args.review_json)),
            )
        else:
            report = build_challenge_report(
                args.root,
                license_receipt=Path(args.license_receipt) if args.license_receipt else None,
            )
    except LipsyncChallengeError as exc:
        raise FilmError(str(exc)) from exc
    _emit(report)
    return 0 if report.get("ok", True) else 1


def cmd_capability(args: argparse.Namespace) -> int:
    """One-page readiness: TTS / FRW canary summary / optional i2v suggest+apply."""
    from capability_report import CapabilityError, build_capability_report

    root = None
    if getattr(args, "root", None):
        root = Path(args.root).expanduser().resolve()
    try:
        report = build_capability_report(
            root=root,
            run_canary=bool(getattr(args, "run_canary", False)),
            suggest_i2v=bool(getattr(args, "suggest_i2v", False))
            or bool(getattr(args, "apply", False)),
            apply=bool(getattr(args, "apply", False)),
            canary_wait=bool(getattr(args, "canary_wait", False)),
            canary_full=bool(getattr(args, "canary_full", False)),
        )
    except CapabilityError as exc:
        raise FilmError(str(exc)) from exc
    _emit(report)
    return 0 if report.get("ok") else 1


def cmd_tts_ab(args: argparse.Namespace) -> int:
    """A/B TTS for one shot → receipts/tts-ab/ (does not change film-spec)."""
    from tts_ab import TTSAbError, run_tts_ab

    backends = [
        b.strip() for b in str(getattr(args, "backends", "mimo,edge")).split(",") if b.strip()
    ]
    try:
        man = run_tts_ab(
            Path(args.root).expanduser().resolve(),
            shot_id=str(args.shot_id),
            backends=backends,
            voice=getattr(args, "voice", None),
            text=getattr(args, "text", None),
            spec_path=Path(args.spec).expanduser().resolve()
            if getattr(args, "spec", None)
            else None,
        )
    except TTSAbError as exc:
        raise FilmError(str(exc)) from exc
    _emit(man)
    return 0 if man.get("ok") else 1


def cmd_elevenlabs_canary(args: argparse.Namespace) -> int:
    """Run a capped bilingual paid canary, or record its human review."""
    from elevenlabs_canary import ElevenLabsCanaryError, list_voices, review_candidate, run_canary

    try:
        if args.list_voices:
            result = list_voices()
        elif args.review_language or args.decision:
            if not args.review_language or not args.decision:
                raise ElevenLabsCanaryError("review requires --review-language and --decision")
            result = review_candidate(
                Path(args.root), language=args.review_language, decision=args.decision
            )
        else:
            if not args.zh_voice or not args.ja_voice:
                raise ElevenLabsCanaryError("run requires --zh-voice and --ja-voice")
            result = run_canary(
                Path(args.root),
                zh_voice=args.zh_voice,
                ja_voice=args.ja_voice,
                model=args.model,
                confirm_cost=bool(args.confirm_cost),
                max_paid_calls=int(args.max_paid_calls),
            )
    except ElevenLabsCanaryError as exc:
        result = {"ok": False, "status": "blocked", "reason": str(exc)}
    _emit(result)
    return 0 if result.get("ok") else 2


def cmd_tts_rehearse(args: argparse.Namespace) -> int:
    """Probe real VO durations into receipts/tts-rehearsal.json (before bulk or final)."""
    root = Path(args.root).expanduser().resolve()
    try:
        from tts_rehearsal import TTSRehearsalError, register_measured_durations, run_rehearsal
    except ImportError as exc:
        raise FilmError(f"tts_rehearsal unavailable: {exc}") from exc

    try:
        if getattr(args, "register_json", None):
            reg_path = Path(args.register_json).expanduser().resolve()
            data = read_json(reg_path)
            if isinstance(data, dict) and isinstance(data.get("shots"), list):
                items = data["shots"]
            elif isinstance(data, list):
                items = data
            else:
                # read_json always returns dict for non-list files; support raw list
                raw = json.loads(reg_path.read_text(encoding="utf-8"))
                if isinstance(raw, list):
                    items = raw
                elif isinstance(raw, dict) and isinstance(raw.get("shots"), list):
                    items = raw["shots"]
                else:
                    raise FilmError("register-json must be a list or {shots: [...]}")
            # path map vs pure duration register
            if items and all(isinstance(x, dict) and x.get("path") for x in items):
                register_map = {
                    str(x["shot_id"]): Path(str(x["path"])) for x in items if isinstance(x, dict)
                }
                receipt = run_rehearsal(
                    root,
                    spec_path=Path(args.spec).expanduser().resolve() if args.spec else None,
                    backend=getattr(args, "tts_backend", None) or getattr(args, "backend", None),
                    voice=str(getattr(args, "voice", None) or "zh-CN-XiaoxiaoNeural"),
                    register_map=register_map,
                    synthesize=False,
                )
            else:
                receipt = register_measured_durations(
                    root,
                    items,
                    source="register",
                    backend=getattr(args, "tts_backend", None) or getattr(args, "backend", None),
                )
        else:
            if bool(getattr(args, "no_synthesize", False)):
                raise FilmError("--no-synthesize requires --register-json")
            receipt = run_rehearsal(
                root,
                spec_path=Path(args.spec).expanduser().resolve() if args.spec else None,
                backend=getattr(args, "tts_backend", None) or getattr(args, "backend", None),
                voice=str(getattr(args, "voice", None) or "zh-CN-XiaoxiaoNeural"),
                synthesize=True,
            )
    except TTSRehearsalError as exc:
        raise FilmError(str(exc)) from exc

    _emit(receipt)
    return 0 if receipt.get("ok") else 1


def cmd_lipsync_node(args: argparse.Namespace) -> int:
    from config_loader import get_config
    from lipsync_node_client import LipsyncNodeError, health

    cfg = get_config()
    if not cfg.lipsync_node_base_url or not cfg.lipsync_node_token:
        raise FilmError(
            "set AIFILM_LIPSYNC_NODE_BASE_URL and AIFILM_LIPSYNC_NODE_TOKEN in config.env"
        )
    try:
        report = health(cfg.lipsync_node_base_url, cfg.lipsync_node_token)
    except LipsyncNodeError as exc:
        raise FilmError(str(exc)) from exc
    _emit(report)
    return 0 if report.get("ok") else 1



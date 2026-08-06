"""Grok OAuth + generation usage CLI — extracted from aifilm_grok (public cmd strings unchanged).

Commands: grok-oauth | usage
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from util.errors import FilmError


def _emit(obj: dict[str, Any]) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))

def add_oauth_parsers(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    goauth = sub.add_parser(
        "grok-oauth",
        help=(
            "Grok OAuth pack (auth.json): doctor|refresh|chat|image|image-edit|"
            "video|video-status|tts|voices"
        ),
    )
    goauth.add_argument(
        "oauth_action",
        nargs="?",
        default="doctor",
        choices=[
            "doctor",
            "refresh",
            "chat",
            "image",
            "image-edit",
            "video",
            "video-status",
            "tts",
            "voices",
        ],
    )
    goauth.add_argument("--prompt", default=None)
    goauth.add_argument(
        "--root",
        default=None,
        help="Film root; enables exact-first generation usage accounting",
    )
    goauth.add_argument("--shot-id", default="", help="Optional shot id for usage accounting")
    goauth.add_argument("--job-id", default="", help="Optional media queue job id")
    goauth.add_argument("--out", default=None, help="output path (image/video/tts)")
    goauth.add_argument("--model", default=None)
    goauth.add_argument("--system", default=None)
    goauth.add_argument("--aspect", default="9:16")
    goauth.add_argument("--deep", action="store_true", help="doctor: also probe TTS voices")
    goauth.add_argument("--json", action="store_true", dest="json_mode", help="chat: JSON mode")
    goauth.add_argument("--image", default=None, help="input still for image-edit / video I2V")
    goauth.add_argument("--ref", action="append", default=[], help="extra reference image(s)")
    goauth.add_argument("--duration", type=int, default=6, help="video duration seconds")
    goauth.add_argument(
        "--resolution",
        default=None,
        help="video: 480p|720p|1080p; image: 1k|2k",
    )
    goauth.add_argument("--wait", action="store_true", help="video: poll until done")
    goauth.add_argument("--timeout", type=float, default=600.0, help="video poll timeout sec")
    goauth.add_argument("--request-id", default=None, dest="request_id")
    goauth.add_argument(
        "--generation-id",
        default=None,
        dest="generation_id",
        help="Tracking id returned by video submit; required to finish async accounting",
    )
    goauth.add_argument("--text", default=None, help="tts text")
    goauth.add_argument("--text-file", default=None, dest="text_file")
    goauth.add_argument("--voice", default=None, help="tts voice_id (default eve)")
    goauth.add_argument("--language", default=None, help="tts language (default zh)")
    goauth.add_argument("--speed", type=float, default=None, help="tts speed 0.7–1.5")
    goauth.add_argument("--timestamps", action="store_true", help="tts character timestamps")

    usage = sub.add_parser(
        "usage",
        help="Exact-first T2I/I2V/TTS request counts, tokens and provider costs",
    )
    usage_sub = usage.add_subparsers(dest="usage_action", required=True)
    usage_status_p = usage_sub.add_parser("status", help="Summarize one film usage ledger")
    usage_status_p.add_argument("--root", required=True)
    usage_list_p = usage_sub.add_parser("list", help="List each generation request")
    usage_list_p.add_argument("--root", required=True)
    usage_list_p.add_argument(
        "--operation",
        choices=("t2i", "image_edit", "i2v", "t2v", "tts"),
        default=None,
    )
    usage_list_p.add_argument(
        "--format",
        choices=("json", "table"),
        default="json",
        dest="output_format",
    )
    usage_summary_p = usage_sub.add_parser(
        "summary", help="Aggregate ledgers below one explicit projects directory"
    )
    usage_summary_p.add_argument("--scan-root", required=True)
    usage_record_p = usage_sub.add_parser(
        "record", help="Record one native/manual generation without inventing missing usage"
    )
    usage_record_p.add_argument("--root", required=True)
    usage_record_p.add_argument(
        "--operation",
        required=True,
        choices=("t2i", "image_edit", "i2v", "t2v", "tts"),
    )
    usage_record_p.add_argument("--provider", required=True)
    usage_record_p.add_argument("--model", default="")
    usage_record_p.add_argument(
        "--status",
        required=True,
        choices=("succeeded", "failed", "moderated"),
    )
    usage_record_p.add_argument(
        "--measurement",
        choices=("unknown", "manual_exact", "local_zero"),
        default="unknown",
    )
    usage_record_p.add_argument("--provider-request-id", default="")
    usage_record_p.add_argument("--output", default="")
    usage_record_p.add_argument("--idempotency-key", default="")
    usage_record_p.add_argument("--shot-id", default="")
    usage_record_p.add_argument("--job-id", default="")
    usage_record_p.add_argument("--input-tokens", type=int, default=None)
    usage_record_p.add_argument("--output-tokens", type=int, default=None)
    usage_record_p.add_argument("--total-tokens", type=int, default=None)
    usage_record_p.add_argument("--cost-in-usd-ticks", type=int, default=None)


def cmd_grok_oauth(args: argparse.Namespace) -> int:
    """Grok OAuth pack (chat/image/edit/video/tts) via ~/.grok/auth.json."""
    from grok_oauth import (
        GrokOAuthError,
        chat_completion,
        get_access_token,
        images_edit,
        images_generate,
        probe,
        tts_list_voices,
        tts_speak,
        video_generate,
        video_status,
        video_submit,
        video_wait,
    )

    action = str(getattr(args, "oauth_action", None) or "doctor")
    usage_root = getattr(args, "root", None)
    shot_id = str(getattr(args, "shot_id", "") or "")
    job_id = str(getattr(args, "job_id", "") or "")
    try:
        if action == "doctor":
            rep = probe(deep=bool(getattr(args, "deep", False)))
            _emit(rep)
            return 0 if rep.get("ok") else 1
        if action == "refresh":
            tok = get_access_token(force_refresh=True, persist=True)
            _emit(
                {
                    "ok": True,
                    "refreshed": tok.get("refreshed"),
                    "ttl_sec": tok.get("ttl_sec"),
                    "expires_at": tok.get("expires_at"),
                    "source": tok.get("source"),
                    "email": tok.get("email"),
                }
            )
            return 0
        if action == "chat":
            prompt = getattr(args, "prompt", None)
            if not prompt:
                raise FilmError("grok-oauth chat requires --prompt")
            _emit(
                chat_completion(
                    str(prompt),
                    model=getattr(args, "model", None),
                    system=getattr(args, "system", None),
                    json_mode=bool(getattr(args, "json_mode", False)),
                )
            )
            return 0
        if action == "image":
            prompt = getattr(args, "prompt", None)
            out = getattr(args, "out", None)
            if not prompt or not out:
                raise FilmError("grok-oauth image requires --prompt and --out")
            _emit(
                images_generate(
                    str(prompt),
                    out=Path(out),
                    model=getattr(args, "model", None),
                    aspect_ratio=getattr(args, "aspect", None) or "9:16",
                    resolution=getattr(args, "resolution", None),
                    usage_root=usage_root,
                    shot_id=shot_id,
                    job_id=job_id,
                )
            )
            return 0
        if action == "image-edit":
            prompt = getattr(args, "prompt", None)
            image = getattr(args, "image", None)
            out = getattr(args, "out", None)
            if not prompt or not image or not out:
                raise FilmError("grok-oauth image-edit requires --image --prompt --out")
            refs = list(getattr(args, "ref", None) or []) or None
            _emit(
                images_edit(
                    str(prompt),
                    image=str(image),
                    out=Path(out),
                    model=getattr(args, "model", None),
                    aspect_ratio=getattr(args, "aspect", None),
                    extra_images=refs,
                    usage_root=usage_root,
                    shot_id=shot_id,
                    job_id=job_id,
                )
            )
            return 0
        if action == "video":
            prompt = getattr(args, "prompt", None)
            image = getattr(args, "image", None)
            out = getattr(args, "out", None)
            refs = list(getattr(args, "ref", None) or []) or None
            if getattr(args, "wait", False):
                if not out:
                    raise FilmError("grok-oauth video --wait requires --out")
                _emit(
                    video_generate(
                        str(prompt) if prompt else None,
                        image=str(image) if image else None,
                        out=Path(out),
                        model=getattr(args, "model", None),
                        duration=int(getattr(args, "duration", 6) or 6),
                        aspect_ratio=getattr(args, "aspect", None) or "9:16",
                        resolution=getattr(args, "resolution", None) or "720p",
                        reference_images=refs,
                        timeout_sec=float(getattr(args, "timeout", 600) or 600),
                        usage_root=usage_root,
                        shot_id=shot_id,
                        job_id=job_id,
                    )
                )
            else:
                _emit(
                    video_submit(
                        str(prompt) if prompt else None,
                        image=str(image) if image else None,
                        model=getattr(args, "model", None),
                        duration=int(getattr(args, "duration", 6) or 6),
                        aspect_ratio=getattr(args, "aspect", None) or "9:16",
                        resolution=getattr(args, "resolution", None) or "720p",
                        reference_images=refs,
                        usage_root=usage_root,
                        shot_id=shot_id,
                        job_id=job_id,
                    )
                )
            return 0
        if action == "video-status":
            rid = getattr(args, "request_id", None)
            if not rid:
                raise FilmError("grok-oauth video-status requires --request-id")
            out = getattr(args, "out", None)
            if getattr(args, "wait", False) or out:
                _emit(
                    video_wait(
                        str(rid),
                        out=Path(out) if out else None,
                        timeout_sec=float(getattr(args, "timeout", 600) or 600),
                        usage_root=usage_root,
                        generation_id=getattr(args, "generation_id", None),
                    )
                )
            else:
                _emit(
                    video_status(
                        str(rid),
                        usage_root=usage_root,
                        generation_id=getattr(args, "generation_id", None),
                    )
                )
            return 0
        if action == "tts":
            text = getattr(args, "text", None)
            text_file = getattr(args, "text_file", None)
            out = getattr(args, "out", None)
            if text_file:
                text = Path(str(text_file)).expanduser().read_text(encoding="utf-8")
            if not text or not out:
                raise FilmError("grok-oauth tts requires --text/--text-file and --out")
            _emit(
                tts_speak(
                    str(text),
                    out=Path(out),
                    voice_id=getattr(args, "voice", None),
                    language=getattr(args, "language", None),
                    speed=getattr(args, "speed", None),
                    with_timestamps=bool(getattr(args, "timestamps", False)),
                    usage_root=usage_root,
                    shot_id=shot_id,
                    job_id=job_id,
                )
            )
            return 0
        if action == "voices":
            _emit(tts_list_voices())
            return 0
    except GrokOAuthError as exc:
        raise FilmError(str(exc)) from exc
    raise FilmError(f"unknown grok-oauth action {action!r}")



def cmd_generation_usage(args: argparse.Namespace) -> int:
    from generation_usage import (
        GenerationUsageError,
        format_usage_table,
        manual_record,
        scan_usage,
        usage_list,
        usage_status,
    )

    action = str(getattr(args, "usage_action", "") or "status")
    try:
        if action == "status":
            report = usage_status(Path(args.root))
        elif action == "list":
            report = usage_list(Path(args.root), operation=getattr(args, "operation", None))
            if getattr(args, "output_format", "json") == "table":
                print(format_usage_table(report))
                return 0 if report.get("ok") else 2
        elif action == "summary":
            report = scan_usage(Path(args.scan_root))
        elif action == "record":
            report = {
                "ok": True,
                "kind": "generation-usage-record",
                "record": manual_record(
                    Path(args.root),
                    operation=args.operation,
                    provider=args.provider,
                    model=args.model,
                    status=args.status,
                    measurement=args.measurement,
                    provider_request_id=args.provider_request_id,
                    output=Path(args.output) if args.output else None,
                    idempotency_key=args.idempotency_key,
                    shot_id=args.shot_id,
                    job_id=args.job_id,
                    input_tokens=args.input_tokens,
                    output_tokens=args.output_tokens,
                    total_tokens=args.total_tokens,
                    cost_in_usd_ticks=args.cost_in_usd_ticks,
                ),
            }
        else:
            raise FilmError(f"unknown usage action {action!r}")
    except GenerationUsageError as exc:
        raise FilmError(str(exc)) from exc
    _emit(report)
    return 0 if report.get("ok") else 2



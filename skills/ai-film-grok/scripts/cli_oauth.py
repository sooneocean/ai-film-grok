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



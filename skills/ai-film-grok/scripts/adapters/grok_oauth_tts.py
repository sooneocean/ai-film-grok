#!/usr/bin/env python3
"""Grok TTS via OAuth — opt-in quality path (film default remains edge).

  python3 adapters/grok_oauth_tts.py \
    --text "更衣室里，她没回头。" \
    --out audio/vo/shot01.mp3 \
    --voice eve --language zh

Speech tags: [pause] [laugh] <whisper>…</whisper>
Timestamps: --timestamps → sidecar for lipsync/caption.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1]
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from grok_oauth import GrokOAuthError, tts_speak  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Grok OAuth TTS (opt-in)")
    p.add_argument("--text", default=None)
    p.add_argument("--text-file", default=None)
    p.add_argument("--out", required=True)
    p.add_argument("--voice", default=None)
    p.add_argument("--language", default="zh")
    p.add_argument("--speed", type=float, default=None)
    p.add_argument("--timestamps", action="store_true")
    args = p.parse_args(argv)

    text = args.text
    if args.text_file:
        text = Path(args.text_file).expanduser().read_text(encoding="utf-8")
    if not text:
        print(json.dumps({"ok": False, "error": "need --text or --text-file"}, ensure_ascii=False))
        return 2

    try:
        result = tts_speak(
            text,
            out=Path(args.out),
            voice_id=args.voice,
            language=args.language,
            speed=args.speed,
            with_timestamps=bool(args.timestamps),
        )
    except GrokOAuthError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    # drop huge timestamp arrays from stdout summary if present
    summary = {k: v for k, v in result.items() if k != "audio_timestamps"}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())

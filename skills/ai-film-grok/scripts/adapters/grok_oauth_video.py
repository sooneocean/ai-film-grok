#!/usr/bin/env python3
"""Batch Image-to-Video via Grok OAuth (api.x.ai) — offline / media-queue path.

Prefer Grok Build native image_to_video in-session. This adapter is for:
  - unattended bulk after pilot approve
  - CI / scripts with grok login or XAI_API_KEY

  python3 adapters/grok_oauth_video.py \
    --image keyframes/shot01.png \
    --prompt-file prompts/shot01_i2v.txt \
    --out clips/shot01_grok.mp4 \
    --duration 6 --resolution 720p
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1]
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from grok_oauth import GrokOAuthError, video_generate  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Grok OAuth image-to-video (batch)")
    p.add_argument("--image", required=True, help="source keyframe PNG/JPEG")
    p.add_argument("--prompt", default=None)
    p.add_argument("--prompt-file", default=None)
    p.add_argument("--out", required=True)
    p.add_argument("--model", default=None)
    p.add_argument("--duration", type=int, default=6)
    p.add_argument("--aspect", default="9:16")
    p.add_argument("--resolution", default="720p", choices=["480p", "720p", "1080p"])
    p.add_argument("--timeout", type=float, default=600.0)
    args = p.parse_args(argv)

    prompt = args.prompt
    if args.prompt_file:
        prompt = Path(args.prompt_file).expanduser().read_text(encoding="utf-8").strip()
    if not prompt:
        prompt = "subtle natural motion, cinematic, keep identity"

    try:
        result = video_generate(
            prompt,
            image=args.image,
            out=Path(args.out),
            model=args.model,
            duration=args.duration,
            aspect_ratio=args.aspect,
            resolution=args.resolution,
            timeout_sec=args.timeout,
        )
    except GrokOAuthError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())

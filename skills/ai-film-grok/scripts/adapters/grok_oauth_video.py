#!/usr/bin/env python3
"""Batch Image-to-Video via Grok OAuth (api.x.ai) — offline / media-queue path.

Prefer Grok Build native image_to_video in-session. This adapter is for:
  - unattended bulk after pilot approve
  - CI / scripts with grok login or XAI_API_KEY

  python3 adapters/grok_oauth_video.py \
    --image keyframes/shot01.png --ref source/style-ref-hero.png \
    --prompt-file prompts/shot01_i2v.txt \
    --out clips/shot01_grok.mp4 \
    --duration 6 --resolution 720p
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1]
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from grok_oauth import GrokOAuthError, video_generate  # noqa: E402


class GrokOAuthVideoProvider:
    """Registry-facing surface for Grok OAuth image-to-video generation."""

    def image_to_video(self, prompt: str, image: str | Path, out: Path, **kwargs):
        return _retry_video_generate(prompt, image=str(image), out=out, **kwargs)


def _retry_video_generate(prompt, **kwargs):
    """Retry video_generate with exponential backoff on 429 rate limits."""
    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        try:
            return video_generate(prompt, **kwargs)
        except GrokOAuthError as exc:
            msg = str(exc).lower()
            if "429" in msg or "rate limit" in msg or "too many requests" in msg:
                if attempt < max_attempts:
                    wait = 2**attempt  # 2s, 4s
                    print(
                        json.dumps(
                            {
                                "ok": False,
                                "error": str(exc),
                                "retry_after": wait,
                                "attempt": attempt,
                            },
                            ensure_ascii=False,
                        )
                    )
                    time.sleep(wait)
                    continue
            raise
    raise GrokOAuthError("video_generate: max retries exhausted")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Grok OAuth image-to-video (batch)")
    p.add_argument("--image", required=True, help="source keyframe PNG/JPEG")
    p.add_argument(
        "--ref",
        action="append",
        default=[],
        help="additional reference image; repeat for reference_to_video (e.g. uploaded style anchor)",
    )
    p.add_argument("--prompt", default=None)
    p.add_argument("--prompt-file", default=None)
    p.add_argument("--out", required=True)
    p.add_argument("--model", default=None)
    p.add_argument("--duration", type=int, default=6)
    p.add_argument("--aspect", default="9:16")
    p.add_argument("--resolution", default="720p", choices=["480p", "720p", "1080p"])
    p.add_argument("--timeout", type=float, default=600.0)
    p.add_argument("--root", default=None)
    p.add_argument("--shot-id", default="")
    p.add_argument("--job-id", default="")
    args = p.parse_args(argv)

    prompt = args.prompt
    if args.prompt_file:
        prompt = Path(args.prompt_file).expanduser().read_text(encoding="utf-8").strip()
    if not prompt:
        prompt = "subtle natural motion, cinematic, keep identity"

    try:
        result = _retry_video_generate(
            prompt,
            image=args.image,
            reference_images=list(args.ref or []) or None,
            out=Path(args.out),
            model=args.model,
            duration=args.duration,
            aspect_ratio=args.aspect,
            resolution=args.resolution,
            timeout_sec=args.timeout,
            usage_root=args.root,
            shot_id=args.shot_id,
            job_id=args.job_id,
        )
    except GrokOAuthError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())

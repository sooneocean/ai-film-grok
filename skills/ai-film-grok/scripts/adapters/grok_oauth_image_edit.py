#!/usr/bin/env python3
"""Image edit via Grok OAuth — offline cast-lock / keyframe path.

In-session prefer image_edit tool. Batch:
  python3 adapters/grok_oauth_image_edit.py \
    --image cast/hero-v1.png \
    --prompt "same face, locker room, 9:16, no text" \
    --out keyframes/shot01.png
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1]
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from grok_oauth import GrokOAuthError, images_edit  # noqa: E402


class GrokOAuthImageEditProvider:
    """Registry-facing surface for Grok OAuth image editing."""

    def edit(self, prompt: str, image: str | Path, out: Path, **kwargs):
        return images_edit(prompt, image=str(image), out=out, **kwargs)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Grok OAuth image edit")
    p.add_argument("--image", required=True)
    p.add_argument("--prompt", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--model", default=None)
    p.add_argument("--aspect", default=None)
    p.add_argument("--ref", action="append", default=[])
    p.add_argument("--root", default=None)
    p.add_argument("--shot-id", default="")
    p.add_argument("--job-id", default="")
    args = p.parse_args(argv)

    try:
        result = images_edit(
            args.prompt,
            image=args.image,
            out=Path(args.out),
            model=args.model,
            aspect_ratio=args.aspect,
            extra_images=list(args.ref or []) or None,
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

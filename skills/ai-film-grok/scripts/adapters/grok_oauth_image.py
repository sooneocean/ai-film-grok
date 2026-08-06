#!/usr/bin/env python3
"""Still generation via Grok OAuth (api.x.ai) — offline / batch fallback.

In Grok Build sessions prefer native image_gen / image_edit tools.
This adapter uses ~/.grok/auth.json (grok login) or XAI_API_KEY.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# allow import sibling
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from grok_oauth import GrokOAuthError, images_generate, probe  # noqa: E402


class GrokOAuthImageProvider:
    """Registry-facing surface for Grok OAuth still generation."""

    def generate(self, prompt: str, out: Path, **kwargs):
        return images_generate(prompt, out=out, **kwargs)

    def edit(self, prompt: str, image: str | Path, out: Path, **kwargs):
        from grok_oauth import images_edit

        return images_edit(prompt, image=str(image), out=out, **kwargs)


def main() -> int:
    p = argparse.ArgumentParser(description="Grok OAuth text-to-image")
    p.add_argument("--prompt", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--model", default=None)
    p.add_argument("--aspect", default="9:16")
    p.add_argument("--root", default=None)
    p.add_argument("--shot-id", default="")
    p.add_argument("--job-id", default="")
    p.add_argument("--doctor", action="store_true")
    args = p.parse_args()
    if args.doctor:
        import json

        print(json.dumps(probe(), ensure_ascii=False, indent=2))
        return 0 if probe().get("ok") else 1
    try:
        result = images_generate(
            args.prompt,
            out=Path(args.out),
            model=args.model,
            aspect_ratio=args.aspect,
            usage_root=args.root,
            shot_id=args.shot_id,
            job_id=args.job_id,
        )
    except GrokOAuthError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(result.get("path"))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())

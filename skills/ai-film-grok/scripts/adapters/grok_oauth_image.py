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


def main() -> int:
    p = argparse.ArgumentParser(description="Grok OAuth text-to-image")
    p.add_argument("--prompt", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--model", default=None)
    p.add_argument("--aspect", default="9:16")
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
        )
    except GrokOAuthError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(result.get("path"))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())

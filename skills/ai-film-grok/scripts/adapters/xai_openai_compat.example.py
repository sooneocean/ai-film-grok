#!/usr/bin/env python3
"""Optional xAI OpenAI-compatible client skeleton (OFF default path).

Grok Build sessions should use native image_gen / image_edit / image_to_video tools.
Use this only for offline scripts / CI with XAI_API_KEY in config.env (chmod 600).

Install (example): pip install openai
Docs: https://docs.x.ai — verify base_url and model ids before production.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def _load_config_env() -> None:
    cfg = (Path(__file__).resolve().parents[2] / "config.env" if (Path(__file__).resolve().parents[2] / "config.env").is_file() else Path.home() / ".grok/skills/ai-film-grok/config.env")
    if not cfg.is_file():
        return
    for line in cfg.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def main() -> int:
    _load_config_env()
    p = argparse.ArgumentParser(description="xAI OpenAI-compat smoke (optional)")
    p.add_argument("--prompt", default="One-line logline for a 60s vertical short.")
    p.add_argument("--model", default=os.environ.get("XAI_MODEL", "grok-4"))
    args = p.parse_args()

    key = (os.environ.get("XAI_API_KEY") or os.environ.get("xai_api_key") or "").strip()
    if not key:
        print("XAI_API_KEY not set — native Grok Build tools need no SDK.", file=sys.stderr)
        return 2

    try:
        from openai import OpenAI
    except ImportError:
        print("pip install openai  # and set XAI_API_KEY", file=sys.stderr)
        return 2

    base = (
        os.environ.get("XAI_BASE_URL")
        or os.environ.get("OPENAI_BASE_URL")
        or "https://api.x.ai/v1"
    ).rstrip("/")
    client = OpenAI(api_key=key, base_url=base)
    # Chat smoke — models/params change; check docs.x.ai
    resp = client.chat.completions.create(
        model=args.model,
        messages=[
            {
                "role": "system",
                "content": "You output concise film production JSON only.",
            },
            {"role": "user", "content": args.prompt},
        ],
    )
    text = (resp.choices[0].message.content or "").strip()
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

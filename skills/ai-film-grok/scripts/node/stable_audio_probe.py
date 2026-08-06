#!/usr/bin/env python3
"""Verify the pinned local Stable Audio checkpoint and adapter."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

MODEL = "stabilityai/stable-audio-open-1.0"
LICENSE = "Stability AI Community License"


from util import sha256_file


def main() -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--model-root", required=True)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--adapter", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--license", required=True)
    args = parser.parse_args()
    root_input = Path(args.model_root).expanduser()
    checkpoint_input = Path(args.checkpoint).expanduser()
    adapter_input = Path(args.adapter).expanduser()
    if any(path.is_symlink() for path in (root_input, checkpoint_input, adapter_input)):
        raise SystemExit("symlinks are not accepted")
    root = root_input.resolve(strict=True)
    checkpoint = checkpoint_input.resolve(strict=True)
    adapter = adapter_input.resolve(strict=True)
    if not root.is_dir() or not checkpoint.is_file() or not adapter.is_file():
        raise SystemExit("invalid Stable Audio provenance paths")
    try:
        checkpoint.relative_to(root)
    except ValueError as exc:
        raise SystemExit("checkpoint must be inside model root") from exc
    if args.model != MODEL or args.license != LICENSE:
        raise SystemExit("unexpected Stable Audio model or license")
    print(
        json.dumps(
            {
                "ok": True,
                "model": MODEL,
                "license": LICENSE,
                "checkpoint_sha256": sha256_file(checkpoint),
                "adapter_sha256": sha256_file(adapter),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Audited one-shot adapter for a pinned LatentSync 1.6 checkout."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", required=True)
    parser.add_argument("--audio", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--inference-steps", type=int, default=20)
    parser.add_argument("--guidance-scale", type=float, default=1.5)
    parser.add_argument("--deepcache", choices=("0", "1"), default="1")
    args = parser.parse_args()

    root = Path(os.environ.get("LATENTSYNC_ROOT", "/home/user/LatentSync")).resolve()
    video = Path(args.video).resolve()
    audio = Path(args.audio).resolve()
    out = Path(args.out).resolve()
    config = root / "configs" / "unet" / "stage2_512.yaml"
    checkpoint = root / "checkpoints" / "latentsync_unet.pt"
    if not root.is_dir() or not config.is_file() or not checkpoint.is_file():
        raise SystemExit("LatentSync checkout, config, or checkpoint is missing")
    if not video.is_file() or not audio.is_file():
        raise SystemExit("LatentSync input is missing")
    if not 1 <= args.inference_steps <= 100 or not 0.1 <= args.guidance_scale <= 10:
        raise SystemExit("LatentSync parameters are invalid")
    out.parent.mkdir(parents=True, exist_ok=True)
    candidate = out.with_name(f"{out.stem}.adapter{out.suffix}")
    command = [
        sys.executable,
        "-m",
        "scripts.inference",
        "--unet_config_path",
        str(config),
        "--inference_ckpt_path",
        str(checkpoint),
        "--inference_steps",
        str(args.inference_steps),
        "--guidance_scale",
        str(args.guidance_scale),
        "--video_path",
        str(video),
        "--audio_path",
        str(audio),
        "--video_out_path",
        str(candidate),
        "--temp_dir",
        str(out.parent / "latentsync-temp"),
    ]
    if args.deepcache == "1":
        command.append("--enable_deepcache")
    try:
        completed = subprocess.run(command, cwd=root, check=False)
    except OSError:
        return 75
    if completed.returncode != 0:
        return 70
    if not candidate.is_file() or candidate.stat().st_size < 16:
        raise SystemExit("LatentSync produced no MP4")
    candidate.replace(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

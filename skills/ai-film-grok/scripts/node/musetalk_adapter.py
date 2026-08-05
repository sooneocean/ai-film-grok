#!/usr/bin/env python3
"""Audited one-shot MuseTalk 1.5 adapter for the RTX lip-sync node."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", required=True)
    parser.add_argument("--audio", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument(
        "--root",
        default=os.environ.get("MUSETALK_ROOT", "/home/user/MuseTalk"),
        help="clean, hash-pinned MuseTalk checkout",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    video = Path(args.video).resolve()
    audio = Path(args.audio).resolve()
    out = Path(args.out).resolve()
    inference = root / "scripts" / "inference.py"
    unet = root / "models" / "musetalkV15" / "unet.pth"
    unet_config = root / "models" / "musetalkV15" / "musetalk.json"
    whisper = root / "models" / "whisper"
    if not all(path.exists() for path in (inference, unet, unet_config, whisper)):
        raise SystemExit("MuseTalk checkout or v1.5 models are missing")
    if not video.is_file() or not audio.is_file():
        raise SystemExit("MuseTalk input is missing")

    work = out.parent / "musetalk-work"
    work.mkdir(parents=True, exist_ok=True)
    normalized = work / "input-25fps.mp4"
    try:
        normalized_run = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-v",
                "error",
                "-i",
                str(video),
                "-an",
                "-r",
                "25",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                str(normalized),
            ],
            check=False,
            timeout=600,
        )
    except subprocess.TimeoutExpired:
        return 76
    except OSError:
        return 75
    if normalized_run.returncode != 0:
        return 70
    config = work / "inference.json"
    config.write_text(
        json.dumps(
            {
                "task_0": {
                    "video_path": str(normalized),
                    "audio_path": str(audio),
                    "result_name": "candidate.mp4",
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    results = work / "results"
    try:
        timeout_sec = float(os.environ.get("AIFILM_MUSETALK_TIMEOUT", "3600") or 3600)
        timeout_sec = max(120.0, timeout_sec)
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "scripts.inference",
                "--inference_config",
                str(config),
                "--result_dir",
                str(results),
                "--unet_model_path",
                str(unet),
                "--unet_config",
                str(unet_config),
                "--whisper_dir",
                str(whisper),
                "--version",
                "v15",
                "--fps",
                "25",
                "--use_float16",
                "--ffmpeg_path",
                str(Path(shutil.which("ffmpeg") or "/usr/bin/ffmpeg").parent),
            ],
            cwd=root,
            check=False,
            timeout=timeout_sec,
        )
    except subprocess.TimeoutExpired:
        return 76
    except OSError:
        return 75
    if completed.returncode != 0:
        return 70
    candidate = results / "v15" / "candidate.mp4"
    if not candidate.is_file() or candidate.stat().st_size < 16:
        raise SystemExit("MuseTalk produced no MP4")
    out.parent.mkdir(parents=True, exist_ok=True)
    candidate.replace(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

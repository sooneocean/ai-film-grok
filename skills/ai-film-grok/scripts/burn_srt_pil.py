#!/usr/bin/env python3
"""Burn a sidecar SRT into an MP4 using PIL overlays (no libass).

P0 lesson: lessons-2026-07-23-subs-always-burn-hard.md
HyperFrames final often ships with --subs off; this is the recovery path when
the host ffmpeg has no subtitles/ass filter.

Usage:
  python3 burn_srt_pil.py --video out/film_final.mp4 --srt out/final.srt --out out/film_final.mp4
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

from security_policy import minimal_subprocess_env


def _parse_ts(s: str) -> float:
    h, m, rest = s.split(":")
    sec, ms = rest.replace(",", ".").split(".")
    return int(h) * 3600 + int(m) * 60 + int(sec) + int(ms) / (10 ** len(ms))


def parse_srt(text: str) -> list[dict]:
    cues: list[dict] = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = [ln for ln in block.splitlines() if ln.strip()]
        if len(lines) < 2:
            continue
        tline = next((ln for ln in lines if "-->" in ln), None)
        if not tline:
            continue
        a, b = [x.strip() for x in tline.split("-->")]
        body = "\n".join(lines[lines.index(tline) + 1 :]).strip()
        if body:
            cues.append({"start": _parse_ts(a), "end": _parse_ts(b), "text": body})
    return cues


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True, type=Path)
    ap.add_argument("--srt", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--width", type=int, default=720)
    ap.add_argument("--height", type=int, default=1280)
    ap.add_argument("--batch", type=int, default=8)
    args = ap.parse_args()

    scripts = Path(__file__).resolve().parent
    sys.path.insert(0, str(scripts))
    from render_final import resolve_font, sub_png  # type: ignore

    cues = parse_srt(args.srt.read_text(encoding="utf-8"))
    if not cues:
        print("no cues in srt", file=sys.stderr)
        return 2

    work = args.out.parent / "_subs_burn"
    overlays = work / "overlays"
    work.mkdir(parents=True, exist_ok=True)
    overlays.mkdir(parents=True, exist_ok=True)
    font = resolve_font()
    for i, cue in enumerate(cues):
        sub_png(
            cue["text"],
            overlays / f"sub_{i:03d}.png",
            width=args.width,
            height=args.height,
            font_path=font,
            dodge=False,
            italic=False,
        )

    tmp = work / "v_in.mp4"
    shutil.copy2(args.video, tmp)
    for start in range(0, len(cues), args.batch):
        chunk = cues[start : start + args.batch]
        inputs: list[str] = ["-i", str(tmp)]
        filters: list[str] = []
        last = "[0:v]"
        oidx = 1
        for j, cue in enumerate(chunk):
            gi = start + j
            inputs += ["-i", str(overlays / f"sub_{gi:03d}.png")]
            out = f"[o{j}]"
            filters.append(
                f"{last}[{oidx}:v]overlay=0:0:enable='between(t,{cue['start']:.3f},{cue['end']:.3f})'{out}"
            )
            last = out
            oidx += 1
        out_path = work / f"v_batch_{start:03d}.mp4"
        cmd = [
            "ffmpeg",
            "-y",
            "-nostdin",
            *inputs,
            "-filter_complex",
            ";".join(filters),
            "-map",
            last,
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-map",
            "0:a?",
            "-c:a",
            "copy",
            str(out_path),
        ]
        try:
            r = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                env=minimal_subprocess_env(),
                timeout=1800,
            )
        except subprocess.TimeoutExpired:
            sys.stderr.write("burn_srt_pil: ffmpeg timed out after 1800s\n")
            return 124
        if r.returncode != 0:
            sys.stderr.write(r.stderr[-3000:])
            return r.returncode
        tmp = out_path

    args.out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(tmp, args.out)
    print(f"ok burned {len(cues)} cues → {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

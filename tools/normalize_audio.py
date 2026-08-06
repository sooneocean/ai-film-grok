#!/usr/bin/env python3
"""Audio normalization helper (stdlib only): remove DC bias and/or peak-normalize
a 16/8-bit WAV. Used to fix generated beds that the QA gate flagged (quiet,
DC-biased) before they go to human review. Writes a new WAV preserving format.

    python3 tools/normalize_audio.py in.wav --out out.wav --peak 0.95
    python3 tools/normalize_audio.py in.wav --no-dc           # keep gain, drop DC
    python3 tools/normalize_audio.py in.wav --in-place       # overwrite

Returns the output path; safe to chain from ingest via --normalize.
"""
import argparse
import math
import os
import sys
import wave
import array


def normalize_wav(src, dst=None, target_peak=0.95, remove_dc=True, in_place=False):
    """Read src, optionally remove DC, scale so |peak| == target_peak, write dst.

    dst defaults to src + ".norm.wav" unless in_place. Returns the output path.
    """
    if in_place:
        dst = src
    elif dst is None:
        base, ext = os.path.splitext(src)
        dst = base + ".norm" + ext

    w = wave.open(src, "rb")
    sr = w.getframerate()
    ch = w.getnchannels()
    sw = w.getsampwidth()
    n = w.getnframes()
    data = w.readframes(n)
    w.close()

    if sw == 2:
        vals = array.array("h")
        vals.frombytes(data)
    elif sw == 1:
        vals = array.array("B")
        vals.frombytes(data)
        vals = array.array("h", (v - 128 for v in vals))
    else:
        raise ValueError(f"unsupported sample width {sw}")

    # DC removal: subtract the mean (centers the waveform at zero)
    if remove_dc and vals:
        mean = sum(vals) / len(vals)
        vals = array.array("h", (int(round(v - mean)) for v in vals))

    # peak scale
    peak = max((abs(v) for v in vals), default=0)
    if peak == 0:
        # silently silent file — nothing to normalize, just copy
        if not in_place:
            w2 = wave.open(dst, "wb")
            w2.setnchannels(ch); w2.setsampwidth(sw); w2.setframerate(sr)
            w2.writeframes(data); w2.close()
        return dst
    scale = (target_peak * 32767.0) / peak
    # guard: never amplify a clip beyond the source's own headroom absurdly
    scale = min(scale, 8.0)
    out = array.array("h", (max(-32768, min(32767, int(round(v * scale)))) for v in vals))

    w2 = wave.open(dst, "wb")
    w2.setnchannels(ch); w2.setsampwidth(2); w2.setframerate(sr)
    w2.writeframes(out.tobytes()); w2.close()
    return dst


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("--out")
    ap.add_argument("--peak", type=float, default=0.95)
    ap.add_argument("--no-dc", action="store_true", help="skip DC removal")
    ap.add_argument("--in-place", action="store_true", help="overwrite src")
    args = ap.parse_args()
    if not os.path.exists(args.src):
        print(f"ERROR: {args.src} not found", file=sys.stderr)
        sys.exit(2)
    dst = normalize_wav(args.src, dst=args.out, target_peak=args.peak,
                        remove_dc=not args.no_dc, in_place=args.in_place)
    print(f"normalized -> {dst} (peak={args.peak}, dc={'off' if args.no_dc else 'removed'})")


if __name__ == "__main__":
    main()

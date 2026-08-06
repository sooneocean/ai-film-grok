#!/usr/bin/env python3
"""Audio quality gate for generated assets (film-ready check).

Runs before an ingested asset is allowed to auto-approve into the library.
Pure stdlib (no numpy):

HARD GATES (block auto-approve, set ok=False):
  - peak in [peak_min, peak_max]   (avoid clipping / near-silence)
  - rms >= rms_min                 (not inaudibly quiet)
  - silence_ratio <= silence_max   (beds shouldn't be mostly silent)
  - duration within [duration_min, requested +/- duration_tol]

ADVISORY SIGNALS (reported, never block — need human ears):
  - zcr         cheap brightness proxy (hissy / very bright beds)
  - dc_offset   DC bias; normalize_audio.py can remove it
  - lufs_est    ITU-R BS.1770-4 K-weighted loudness estimate
  - loop_score  seamless-loop continuity (head/tail energy + edge match)
  - near_dup    cosine vs an already-approved catalog fingerprint

Keeps bad generations (clipping, near-silent, mostly-silent, wrong length)
out of the catalog instead of auto-approving them blindly, while surfacing
the softer film-mix concerns to a human reviewer.

    python3 tools/qa_audio.py pending/foo.wav --duration 30
    python3 tools/qa_audio.py pending/foo.wav --strict   # non-zero exit on FAIL
"""
import argparse
import json
import math
import os
import sys
import wave
import array

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pipeline_lib import analyze_wav, cosine, extract_fingerprint

# ITU-R BS.1770-4 K-weighting coefficients (nominal fs=48 kHz). Used for the
# LUFS estimate — advisory only, so small fs mismatch is acceptable.
_K_SHELF_B = (1.535124859, -2.691696189, 1.198392810)
_K_SHELF_A = (1, -1.690659293, 0.732480774)
_K_HP_B = (1.0, -2.0, 1.0)
_K_HP_A = (1, -1.990047455, 0.990072261)

DEFAULTS = {
    "peak_min": 0.55, "peak_max": 0.99,   # avoid clipping and near-silence
    "rms_min": 0.008,                     # not inaudibly quiet
    "silence_max": 0.10,                  # beds shouldn't be >10% silent
    "duration_min": 1.0,
    "duration_tol": 0.15,                 # +/-15% of requested duration
    # --- advisory thresholds (do NOT set ok=False) ---
    "zcr_max": 0.25,                      # very bright / hissy flagged
    "dc_max": 0.01,                       # 1% DC bias flagged
    "lufs_loud": -8.0,                    # hotter than this flagged
    "lufs_quiet": -30.0,                  # quieter than this flagged
    "loop_min": 0.80,                     # below this flagged (discontinuity)
    "near_dup_sim": 0.98,                 # cosine >= this flagged (advisory)
}


def _read_mono(path):
    """Return (sample_rate, channels, mono_int_array) from a 16/8-bit WAV."""
    w = wave.open(path, "rb")
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
        return sr, ch, array.array("h")
    if ch > 1:
        vals = vals[::ch]
    return sr, ch, vals


def _rms(vals):
    if not vals:
        return 0.0
    return math.sqrt(sum(v * v for v in vals) / len(vals)) / 32767.0


def _dc_offset(vals):
    if not vals:
        return 0.0
    return sum(vals) / len(vals) / 32767.0


def _zcr(vals, sr):
    """Zero-crossing rate as a cheap brightness proxy."""
    if len(vals) < 2:
        return 0.0
    cross = sum(1 for i in range(1, len(vals)) if (vals[i] >= 0) != (vals[i - 1] >= 0))
    return cross / (len(vals) - 1)


def _biquad(x, b, a):
    """Direct-form-II-transposed biquad. a = (1, a1, a2) per scipy convention."""
    b0, b1, b2 = b
    a1, a2 = a[1], a[2]
    y = [0.0] * len(x)
    z1 = z2 = 0.0
    for i in range(len(x)):
        xi = x[i]
        yi = b0 * xi + z1
        z1 = b1 * xi - a1 * yi + z2
        z2 = b2 * xi - a2 * yi
        y[i] = yi
    return y


def _lufs_estimate(vals, sr):
    """ITU-R BS.1770-4 K-weighted loudness estimate (LUFS), stdlib only.

    Applies the K-weighting pre-filter (high shelf + high pass), then the
    overall (ungated) loudness. Downsamples by 4 for speed — advisory only.
    Returns a LUFS value (negative dB); -70.0 if silent.
    """
    if not vals:
        return -70.0
    # downsample 4x: K-weighting is heavily smoothed, accuracy loss negligible
    x = [v / 32767.0 for v in vals[::4]]
    if not x:
        return -70.0
    x = _biquad(x, _K_SHELF_B, _K_SHELF_A)
    x = _biquad(x, _K_HP_B, _K_HP_A)
    ms = sum(v * v for v in x) / len(x)
    if ms <= 0:
        return -70.0
    return round(-0.691 + 10.0 * math.log10(ms), 2)


def _loop_score(vals, sr):
    """Seamless-loop continuity score in [0,1].

    Heuristic: reward matched head/tail RMS (so a looped bed doesn't pump)
    and edge samples near zero (so the wrap point doesn't click). Advisory.
    """
    if not vals:
        return 0.0
    win = max(1, int(sr * 0.5))
    if len(vals) < win * 2:
        win = max(1, len(vals) // 2)
    head = vals[:win]
    tail = vals[-win:]
    hr = _rms(head)
    tr = _rms(tail)
    denom = max(hr, tr) or 1e-9
    rms_match = 1.0 - abs(hr - tr) / denom
    first = vals[0] / 32767.0
    last = vals[-1] / 32767.0
    edge = 1.0 - (abs(first) + abs(last)) / 2.0
    return round(max(0.0, min(1.0, 0.6 * rms_match + 0.4 * edge)), 4)


def near_dup_advisory(fp, approved):
    """Return (max_sim, asset_id) of the closest approved fingerprint, or
    (0.0, None). `approved` is a list of (asset_id, fingerprint) tuples."""
    best, best_id = 0.0, None
    for aid, afp in approved:
        if not afp:
            continue
        s = cosine(fp, afp)
        if s > best:
            best, best_id = s, aid
    return best, best_id


def qa_asset(path, spec=None, thresholds=None, approved=None):
    """Run the full QA battery. Returns:

        {ok, metrics:{...}, issues:[hard...], advisories:[soft...], thresholds}

    `ok` reflects ONLY hard gates. `advisories` never affect `ok`.
    `approved` is an optional list of (asset_id, fingerprint) tuples used for
    the near-duplicate check.
    """
    t = dict(DEFAULTS)
    t.update(thresholds or {})
    spec = spec or {}

    m = analyze_wav(path)
    sr, ch, vals = _read_mono(path)
    m["zcr"] = round(_zcr(vals, sr), 4)
    m["dc_offset"] = round(_dc_offset(vals), 6)
    m["lufs_est"] = _lufs_estimate(vals, sr)
    m["loop_score"] = _loop_score(vals, sr)

    issues = []      # HARD — block auto-approve
    advisories = []  # SOFT — human ears

    # --- hard gates ---
    if not (t["peak_min"] <= m["peak"] <= t["peak_max"]):
        issues.append(f"peak {m['peak']} outside [{t['peak_min']},{t['peak_max']}]")
    if m["rms"] < t["rms_min"]:
        issues.append(f"rms {m['rms']} below {t['rms_min']}")
    if m["silence_ratio"] > t["silence_max"]:
        issues.append(f"silence_ratio {m['silence_ratio']} above {t['silence_max']}")
    dur = m["duration_sec"]
    if dur < t["duration_min"]:
        issues.append(f"duration {dur}s below {t['duration_min']}s")
    req = spec.get("duration")
    if req:
        lo, hi = req * (1 - t["duration_tol"]), req * (1 + t["duration_tol"])
        if not (lo <= dur <= hi):
            issues.append(f"duration {dur}s outside requested {req}s +/-{int(t['duration_tol']*100)}%")

    # --- advisory signals ---
    if m["zcr"] > t["zcr_max"]:
        advisories.append(f"zcr {m['zcr']} above {t['zcr_max']} (bright/hissy advisory)")
    if abs(m["dc_offset"]) > t["dc_max"]:
        advisories.append(f"dc_offset {m['dc_offset']} above {t['dc_max']} (bias; normalize to fix)")
    if m["lufs_est"] > t["lufs_loud"]:
        advisories.append(f"lufs_est {m['lufs_est']} hotter than {t['lufs_loud']} (may distort on normalise)")
    elif m["lufs_est"] < t["lufs_quiet"]:
        advisories.append(f"lufs_est {m['lufs_est']} quieter than {t['lufs_quiet']} (low-energy bed)")
    if m["loop_score"] < t["loop_min"]:
        advisories.append(f"loop_score {m['loop_score']} below {t['loop_min']} (head/tail discontinuity)")
    if approved:
        fp = extract_fingerprint(path)
        sim, aid = near_dup_advisory(fp, approved)
        if sim >= t["near_dup_sim"]:
            advisories.append(f"near-duplicate of {aid} (cosine {round(sim, 4)} >= {t['near_dup_sim']})")

    return {"ok": len(issues) == 0, "metrics": m, "issues": issues,
            "advisories": advisories, "thresholds": t}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--duration", type=float, default=None)
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args()
    if not os.path.exists(args.path):
        print(f"ERROR: {args.path} not found", file=sys.stderr)
        sys.exit(2)
    res = qa_asset(args.path, {"duration": args.duration})
    print(json.dumps(res, ensure_ascii=False, indent=2))
    if args.strict and not res["ok"]:
        sys.exit(1)


if __name__ == "__main__":
    main()

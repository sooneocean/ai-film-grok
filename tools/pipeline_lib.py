#!/usr/bin/env python3
"""Shared, self-contained helpers for the aifilm bgm pipeline.

No third-party deps (stdlib only) so every tool can import it the same way
validate_catalog.py stays dependency-free. Centralises the boring bits:
paths, load/save with backup, revision bump, sha256, and a stdlib-only
acoustic fingerprint used when a generator backend does not supply one.
"""
import json
import os
import shutil
import hashlib
import wave
import array
import math
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIB = os.path.join(ROOT, "bgm-library")
CAT = os.path.join(LIB, "catalog.json")
GAP = os.path.join(LIB, "gap-queue.jsonl")
JOBS = os.path.join(LIB, "generation-jobs.jsonl")
GEN = os.path.join(LIB, "generators.json")

# --- state machine contract (single source of truth) -----------------------
ASSET_STATUSES = {"approved", "pending_human_review", "rejected"}
GAP_STATUSES = {"open", "routed_generate", "filled", "rejected"}

# legal asset transitions; anything else is rejected by route.py guardrails
ASSET_TRANSITIONS = {
    "pending_human_review": {"approved", "rejected"},
    "approved": {"rejected"},          # an approved asset can be pulled
    "rejected": set(),                 # terminal
}
# legal gap transitions
GAP_TRANSITIONS = {
    "open": {"routed_generate", "rejected", "filled"},
    "routed_generate": {"filled", "open", "rejected"},  # open = generation failed, retry
    "filled": set(),
    "rejected": set(),
}


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def load_catalog():
    return json.load(open(CAT, encoding="utf-8"))


def save_catalog(cat, backup=True):
    if backup:
        shutil.copy(CAT, CAT + ".bak")
    with open(CAT, "w", encoding="utf-8") as f:
        json.dump(cat, f, indent=2, ensure_ascii=False)


def load_gaps():
    return [json.loads(l) for l in open(GAP, encoding="utf-8") if l.strip()]


def save_gaps(gaps, backup=True):
    if backup:
        shutil.copy(GAP, GAP + ".bak")
    with open(GAP, "w", encoding="utf-8") as f:
        for g in gaps:
            f.write(json.dumps(g, ensure_ascii=False) + "\n")


def load_jobs():
    if not os.path.exists(JOBS):
        return []
    return [json.loads(l) for l in open(JOBS, encoding="utf-8") if l.strip()]


def save_jobs(jobs, backup=True):
    if backup and os.path.exists(JOBS):
        shutil.copy(JOBS, JOBS + ".bak")
    with open(JOBS, "w", encoding="utf-8") as f:
        for j in jobs:
            f.write(json.dumps(j, ensure_ascii=False) + "\n")


def load_generators():
    if not os.path.exists(GEN):
        return {"schema": "aifilm-generators-v1", "backends": {}}
    return json.load(open(GEN, encoding="utf-8"))


def bump(cat):
    cat["revision"] = cat.get("revision", 0) + 1
    cat["updated_at"] = now_iso()


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for blk in iter(lambda: f.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def ensure_dir(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)


def ext_to_codec(ext):
    return {"wav": "wav", "flac": "flac", "mp3": "mp3"}.get(ext.lower().lstrip("."), "unknown")


def extract_fingerprint(wav_path, bins=101):
    """Stdlib-only crude RMS-envelope fingerprint.

    Real generator backends should return a proper acoustic fingerprint in
    their job metadata; this is the fallback so ingest_generated assets still
    satisfy the catalog contract (technical.fingerprint must be list[number]).
    It is deterministic and cosine-comparable, good enough for clustering.
    """
    try:
        w = wave.open(wav_path, "rb")
        n = w.getnframes()
        ch = w.getnchannels()
        sw = w.getsampwidth()
        data = w.readframes(n)
        w.close()
    except Exception:
        return [0.0] * bins
    if sw == 2:
        vals = array.array("h")
        vals.frombytes(data)
    elif sw == 1:
        vals = array.array("B")
        vals.frombytes(data)
        vals = array.array("h", (v - 128 for v in vals))
    else:
        return [0.0] * bins
    if ch > 1:
        vals = vals[::ch]
    total = len(vals)
    if total == 0:
        return [0.0] * bins
    seg = max(1, total // bins)
    fp = []
    for i in range(bins):
        s = i * seg
        e = min(total, (i + 1) * seg)
        chunk = vals[s:e]
        fp.append(math.sqrt(sum(x * x for x in chunk) / len(chunk)) if chunk else 0.0)
    mx = max(fp) or 1.0
    return [x / mx for x in fp]


def can_transition(kind, old, new):
    table = ASSET_TRANSITIONS if kind == "asset" else GAP_TRANSITIONS
    allowed = table.get(old, set())
    return new in allowed


def cosine(a, b):
    n = min(len(a), len(b))
    if n == 0:
        return 0.0
    dot = sum(a[i] * b[i] for i in range(n))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na and nb else 0.0


def analyze_wav(path):
    """Stdlib WAV analysis: sr, channels, duration, peak, rms, silence_ratio.

    Used by ingest (to populate technical.*) and by qa_audio (to gate quality
    before an asset is allowed to auto-approve into the film). Returns a dict.
    """
    w = wave.open(path, "rb")
    sr = w.getframerate()
    ch = w.getnchannels()
    n = w.getnframes()
    sw = w.getsampwidth()
    data = w.readframes(n)
    w.close()
    if sw == 2:
        vals = array.array("h"); vals.frombytes(data)
    elif sw == 1:
        vals = array.array("B"); vals.frombytes(data)
        vals = array.array("h", (v - 128 for v in vals))
    else:
        return {"sample_rate": sr, "channels": ch, "duration_sec": 0,
                "peak": 0, "rms": 0, "silence_ratio": 0}
    if ch > 1:
        vals = vals[::ch]
    total = len(vals)
    if total == 0:
        return {"sample_rate": sr, "channels": ch, "duration_sec": 0,
                "peak": 0, "rms": 0, "silence_ratio": 0}
    peak = max((abs(x) for x in vals), default=0) / 32767.0
    rms = math.sqrt(sum(x * x for x in vals) / total) / 32767.0
    win = max(1, sr // 100)
    silent = 0
    wins = 0
    for i in range(0, total, win):
        chunk = vals[i:i + win]
        if not chunk:
            continue
        wins += 1
        wr = math.sqrt(sum(x * x for x in chunk) / len(chunk)) / 32767.0
        if wr < 0.00316:
            silent += 1
    silence = silent / wins if wins else 0
    return {"sample_rate": sr, "channels": ch, "duration_sec": round(n / sr, 3),
            "peak": round(peak, 6), "rms": round(rms, 6), "silence_ratio": round(silence, 4)}

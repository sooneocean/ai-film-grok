#!/usr/bin/env python3
"""Ingest a generated audio file back into the catalog as a pending asset.

This is the reflux entry point of the generate loop: a backend produced
audio for a gap, and this tool turns it into a first-class catalog entry
(status=pending_human_review), moves it into pending/, recomputes sha256 +
a stdlib fingerprint, bumps revision, re-validates, and marks the source gap
routed_generate (awaiting human approve -> fill). Without this, a generated
file would sit orphaned in pending/ forever — that was the old open loop.

    python3 tools/ingest_generated.py --audio pending/<job>.wav \\
        --source-gap-id <gap_id> --backend acestep --job-id <job_id> \\
        --mood ambient --stem-profile pad --energy 0.35 --duration 30
"""
import argparse
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pipeline_lib import (load_catalog, save_catalog, load_gaps, save_gaps,
                          LIB, now_iso, sha256_file, bump, extract_fingerprint,
                          analyze_wav)
from qa_audio import qa_asset
from normalize_audio import normalize_wav
from tts import tts_qa

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio", required=True)
    ap.add_argument("--source-gap-id", required=True)
    ap.add_argument("--backend", required=True)
    ap.add_argument("--job-id", default="")
    ap.add_argument("--mood", required=True)
    ap.add_argument("--stem-profile", required=True)
    ap.add_argument("--energy", type=float, default=0.35)
    ap.add_argument("--duration", type=float, default=30.0)
    ap.add_argument("--recipe-id", default="")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--asset-kind", default="bgm", choices=("bgm", "tts"),
                    help="lane this asset belongs to (bgm bed or tts voice)")
    ap.add_argument("--normalize", action="store_true",
                    help="remove DC bias + peak-normalize the file before ingest "
                         "(fixes quiet/DC-flagged generations; default off)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    audio = os.path.abspath(args.audio)
    if not os.path.exists(audio):
        print(f"ERROR: audio not found: {audio}", file=sys.stderr); sys.exit(2)

    # Load the catalog now (read-only): we need the approved fingerprints to
    # run the near-duplicate advisory (BGM only), and reuse this object for the
    # write. TTS assets skip the near-dup check (voice ≠ music bed).
    cat = load_catalog()
    approved = [(aid, a.get("technical", {}).get("fingerprint"))
                for aid, a in cat.get("assets", {}).items()
                if a.get("status") == "approved"] if args.asset_kind == "bgm" else []

    # Optional pre-ingest fix: DC removal + peak normalize the generated file
    # in place so quiet / DC-biased beds become film-usable. Skipped on dry-run
    # (it mutates the file). The sha256 below is computed AFTER this step.
    if args.normalize and not args.dry_run:
        audio = normalize_wav(audio, in_place=True, target_peak=0.95, remove_dc=True)
        print(f"  normalized -> {os.path.basename(audio)}")

    sha = sha256_file(audio)
    hid = sha[:8]
    asset_id = f"{args.mood}-{hid}"
    ext = audio.rsplit(".", 1)[-1]
    dst_path = f"pending/{asset_id}.{ext}"
    dst = os.path.join(LIB, dst_path)

    m = analyze_wav(audio)
    sr, ch, dur, peak, rms, silence = (m["sample_rate"], m["channels"],
                                       m["duration_sec"], m["peak"],
                                       m["rms"], m["silence_ratio"])
    fp = extract_fingerprint(audio)
    # QA gate: BGM uses the full music battery; TTS uses the voice variant
    # (loop check suppressed). Hard gates still block auto-approve; the softer
    # film-mix signals (zcr/dc/lufs/loop/near-dup) are advisory only.
    if args.asset_kind == "tts":
        qa = tts_qa(audio, spec={"duration": args.duration})
    else:
        qa = qa_asset(audio, spec={"duration": args.duration}, approved=approved)
    recipe_id = args.recipe_id or f"ingest-{args.backend}-{args.mood}"
    now = now_iso()

    asset = {
        "schema": "aifilm-bgm-asset-v1",
        "asset_id": asset_id,
        "status": "pending_human_review",
        "path": dst_path,
        "sha256": sha,
        "model": args.backend,
        "seed": args.seed,
        "recipe": {
            "recipe_id": recipe_id,
            "mood": args.mood,
            "dramatic_tags": [],
            "energy": args.energy,
            "stem_profile": args.stem_profile,
            "bpm": 72,
            "keyscale": "C major",
            "timesignature": "4/4",
            "duration": args.duration,
        },
        "mood": args.mood,
        "dramatic_tags": [],
        "energy": args.energy,
        "stem_profile": args.stem_profile,
        "bpm": 72,
        "keyscale": "C major",
        "timesignature": "4/4",
        "motif_family": "",
        "series_id": "",
        "parent_asset_id": None,
        "instrumental": True,
        "technical": {
            "ok": True,
            "errors": [],
            "codec": ext,
            "sample_rate": sr,
            "channels": ch,
            "duration_sec": round(dur, 3),
            "peak": round(peak, 6),
            "rms": round(rms, 6),
            "silence_ratio": round(silence, 4),
            "fingerprint": fp,
            "qa": {
                "ok": qa["ok"],
                "issues": qa["issues"],
                "advisories": qa["advisories"],
                "metrics": qa["metrics"],
            },
        },
        "similarity_cluster": asset_id,
        "use_count": 0,
        "asset_kind": args.asset_kind,
        "created_at": now,
        "generated_by": args.backend,
        "generated_from_gap": args.source_gap_id,
    }

    print(f"ingest -> {asset_id} ({dst_path}) from {os.path.basename(audio)}")
    qa_tag = "PASS" if qa["ok"] else f"HOLD ({'; '.join(qa['issues'])})"
    print(f"  qa_audio: {qa_tag}")
    if qa["advisories"]:
        print(f"  qa advisories ({len(qa['advisories'])}):")
        for adv in qa["advisories"]:
            print(f"    - {adv}")
    if args.dry_run:
        print("  (dry-run, no changes written)"); return

    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if os.path.abspath(dst) != audio:
        shutil.move(audio, dst)

    cat["assets"][asset_id] = asset
    bump(cat)
    save_catalog(cat)

    ok = subprocess.run([sys.executable, os.path.join(HERE, "validate_catalog.py"),
                         "--no-sha"], capture_output=True, text=True)
    if ok.returncode != 0:
        print("ERROR: catalog validation failed after ingest; restoring backup",
              file=sys.stderr)
        shutil.copy(os.path.join(LIB, "catalog.json.bak"), os.path.join(LIB, "catalog.json"))
        print(ok.stdout); sys.exit(1)

    gaps = load_gaps()
    for g in gaps:
        if g.get("gap_id") == args.source_gap_id:
            g["status"] = "routed_generate"
            g["routed_backend"] = args.backend
            g["generation_job_id"] = args.job_id
            g["generated_asset_id"] = asset_id
    save_gaps(gaps)
    print(f"  revision -> {cat['revision']}; gap {args.source_gap_id[:12]}… -> routed_generate; validation OK ✓")
    print(f"ASSET_ID={asset_id}")
    return asset_id


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""P3.5 official dialect A/B reburn — densify-era compile + same-seed burns + mean score.

Idle-gated only (zero submit when queue busy). No free-memory unless already idle.
"""
from __future__ import annotations

import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SKILL = ROOT.parents[2]  # skills/ai-film-grok
SEED = 202608074  # P3.5 densify reburn seed (distinct from O3 20260807)
COMFY = "http://127.0.0.1:18188"


def stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def queue() -> dict:
    try:
        with urllib.request.urlopen(f"{COMFY}/queue", timeout=5) as r:
            data = json.loads(r.read().decode())
        run = data.get("queue_running") or []
        pend = data.get("queue_pending") or []
        return {
            "running": len(run),
            "pending": len(pend),
            "idle": len(run) == 0 and len(pend) == 0,
        }
    except Exception as exc:  # noqa: BLE001
        return {"running": None, "pending": None, "idle": False, "error": str(exc)}


def vram() -> dict:
    try:
        with urllib.request.urlopen(f"{COMFY}/system_stats", timeout=5) as r:
            data = json.loads(r.read().decode())
        devs = data.get("devices") or []
        if not devs:
            return {}
        d0 = devs[0]
        free_b = float(d0.get("vram_free") or 0)
        total_b = float(d0.get("vram_total") or 0)
        return {
            "free_gib": round(free_b / (1024**3), 2),
            "total_gib": round(total_b / (1024**3), 2),
            "free_b": free_b,
        }
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


def _setup_path() -> None:
    """Insert package dirs without shadowing stdlib (never put scripts/util first)."""
    scripts = SKILL / "scripts"
    # scripts/ first so `import util` resolves to package; do NOT insert scripts/util
    # as a top-level path (would shadow stdlib subprocess with util.subprocess).
    for sub in (
        "",
        "media",
        "plan",
        "core",
        "spine",
        "assets",
        "gates",
        "audio",
        "post",
        "narrative",
        "cli",
    ):
        p = scripts / sub if sub else scripts
        s = str(p)
        if s not in sys.path:
            sys.path.insert(0, s)


def recompile_prompts() -> list[dict]:
    from h3_official_prompt import (
        compile_official_h3_prompt,
        official_prompt_word_count,
        validate_official_prompt,
    )
    from motion_prompt_spine import build_h3_temporal_prompt
    from util.film_spec import _iter_shots, _load_spec

    spec = _load_spec(ROOT)
    rows: list[dict] = []
    pdir = ROOT / "receipts" / "prompts"
    pdir.mkdir(parents=True, exist_ok=True)
    for shot in _iter_shots(spec):
        sid = str(shot.get("id"))
        dialect = str(shot.get("ab_dialect") or "").lower()
        family = str(shot.get("ab_family") or "")
        work = dict(shot)
        work.setdefault("dsl", {})
        if not isinstance(work["dsl"], dict):
            work["dsl"] = {}
        if dialect == "official":
            work["dsl"]["prompt_format"] = "official"
            work["prompt_format"] = "official"
            text = compile_official_h3_prompt(work, mode="i2v", duration_sec=5.0)
            val = validate_official_prompt(text, mode="i2v")
            (pdir / f"{sid}.i2v.txt").write_text(text + "\n", encoding="utf-8")
            (pdir / f"{sid}.h3.official.txt").write_text(text + "\n", encoding="utf-8")
            rows.append(
                {
                    "shot_id": sid,
                    "family": family,
                    "dialect": dialect,
                    "prompt_chars": len(text),
                    "imd_words": official_prompt_word_count(text, field="imd"),
                    "validate": val,
                }
            )
        else:
            work["dsl"]["prompt_format"] = "timeline"
            work["prompt_format"] = "timeline"
            text = build_h3_temporal_prompt({}, work, mode="i2v", duration_sec=5.0)
            (pdir / f"{sid}.i2v.txt").write_text(text + "\n", encoding="utf-8")
            (pdir / f"{sid}.h3.legacy.txt").write_text(text + "\n", encoding="utf-8")
            rows.append(
                {
                    "shot_id": sid,
                    "family": family,
                    "dialect": dialect,
                    "prompt_chars": len(text),
                    "legacy_timecode": "[0s-" in text,
                }
            )
    (ROOT / "receipts" / "h3-official-p35-compile.json").write_text(
        json.dumps(
            {
                "ok": True,
                "kind": "h3-official-p35-compile",
                "at": stamp(),
                "seed": SEED,
                "plugin_hint": "2.40.94+",
                "rows": rows,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return rows


def measure(path: Path) -> dict:
    from i2v_motion_gate import measure_mean_absdiff

    if not path.is_file():
        return {"mean": None, "error": "missing", "path": str(path)}
    mean = measure_mean_absdiff(path)
    return {
        "mean": float(mean) if mean is not None else None,
        "path": str(path),
        "size": path.stat().st_size,
    }


def winner(leg: float | None, off: float | None, *, eps: float = 0.5) -> str:
    if leg is None or off is None:
        return "unknown"
    if abs(leg - off) <= eps:
        return "tie"
    return "official" if off > leg else "legacy"


def main() -> int:
    _setup_path()
    import time as _time

    # Wait up to 30 min for idle + VRAM floor (no hog: never interrupt others).
    wait_cap = 1800
    waited = 0
    q0 = queue()
    v0 = vram()
    print(f"[{stamp()}] wait capacity start queue={q0} vram={v0}", flush=True)
    while waited < wait_cap:
        q0 = queue()
        v0 = vram()
        free_g = float(v0.get("free_gib") or 0)
        if q0.get("idle") and free_g >= 24.0:
            break
        if q0.get("idle") and free_g < 24.0:
            try:
                req = urllib.request.Request(
                    f"{COMFY}/free",
                    data=json.dumps(
                        {"unload_models": True, "free_memory": True}
                    ).encode(),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                urllib.request.urlopen(req, timeout=90).read()
                print(f"[{stamp()}] free-memory (idle, vram low)", flush=True)
            except Exception as free_exc:  # noqa: BLE001
                print(f"[{stamp()}] free fail: {free_exc}", flush=True)
        _time.sleep(15)
        waited += 15
        if waited % 60 == 0:
            print(f"[{stamp()}] still waiting q={q0} v={v0} t={waited}s", flush=True)

    q0 = queue()
    v0 = vram()
    if not (q0.get("idle") and float(v0.get("free_gib") or 0) >= 24.0):
        out = {
            "status": "OPEN_OPS",
            "ok": False,
            "kind": "h3-official-p35-canary",
            "at": stamp(),
            "queue": q0,
            "vram": v0,
            "reason": "WAIT_CAPACITY_TIMEOUT zero submit (multi-agent GPU no-hog)",
            "waited_sec": waited,
            "partial_takes": [
                str(p)
                for p in sorted((ROOT / "takes").rglob(f"*{SEED}*.mp4"))
                if "704x1280" not in p.name
            ],
        }
        (SKILL / "artifacts" / "2026-08-07-h3-official-p35-canary.json").write_text(
            json.dumps(out, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps(out, indent=2), flush=True)
        return 2

    print(f"[{stamp()}] capacity ready queue={q0} vram={v0}", flush=True)
    compile_rows = recompile_prompts()
    print(f"[{stamp()}] compiled {len(compile_rows)} prompts", flush=True)

    from h3_workflow import run_h3_shot
    from util.film_spec import _iter_shots, _load_spec

    spec = _load_spec(ROOT)
    shots = list(_iter_shots(spec))
    burns: list[dict] = []

    for shot in shots:
        sid = str(shot.get("id"))
        existing = sorted((ROOT / "takes" / sid).glob(f"*{SEED}*.mp4"))
        existing = [p for p in existing if "704x1280" not in p.name]
        if existing:
            burns.append(
                {
                    "shot_id": sid,
                    "ok": True,
                    "skipped_existing": True,
                    "dialect": shot.get("ab_dialect"),
                    "family": shot.get("ab_family"),
                    "clip": str(existing[-1]),
                }
            )
            print(f"[{stamp()}] skip existing {sid} -> {existing[-1].name}", flush=True)
            continue
        # wait up to 15 min for idle + VRAM floor before each missing burn
        import time as _time

        waited = 0
        while waited < 900:
            q = queue()
            vv = vram()
            free_g = float(vv.get("free_gib") or 0)
            if q.get("idle") and free_g >= 24.0:
                break
            if q.get("idle") and free_g < 24.0:
                try:
                    req = urllib.request.Request(
                        f"{COMFY}/free",
                        data=json.dumps(
                            {"unload_models": True, "free_memory": True}
                        ).encode(),
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    )
                    urllib.request.urlopen(req, timeout=90).read()
                except Exception:
                    pass
            _time.sleep(12)
            waited += 12
        q = queue()
        vv = vram()
        if not (q.get("idle") and float(vv.get("free_gib") or 0) >= 24.0):
            burns.append(
                {
                    "shot_id": sid,
                    "ok": False,
                    "reason": "COMFY_BUSY_OR_VRAM",
                    "queue": q,
                    "vram": vv,
                    "dialect": shot.get("ab_dialect"),
                    "family": shot.get("ab_family"),
                }
            )
            print(f"[{stamp()}] capacity miss at {sid} q={q} v={vv}", flush=True)
            continue
        print(
            f"[{stamp()}] burn {sid} dialect={shot.get('ab_dialect')} seed={SEED}",
            flush=True,
        )
        try:
            rep = run_h3_shot(
                ROOT,
                sid,
                mode="i2v",
                register=False,  # canary root may lack full init; takes file is enough
                status="candidate",
                seed=SEED,
                timeout_sec=1800,
                enqueue_queue=False,
                production_stage="pilot",
            )
            # resolve take path
            takes = sorted((ROOT / "takes" / sid).glob(f"*{SEED}*.mp4"))
            if not takes:
                takes = sorted(
                    (ROOT / "takes" / sid).glob("*.mp4"),
                    key=lambda p: p.stat().st_mtime,
                )
            clip = str(takes[-1]) if takes else (
                rep.get("clip_path")
                or rep.get("out")
                or rep.get("take_path")
                or rep.get("plate_path")
            )
            ok = bool(clip) and Path(str(clip)).is_file()
            burns.append(
                {
                    "shot_id": sid,
                    "ok": ok and bool(rep.get("ok", True)),
                    "dialect": shot.get("ab_dialect"),
                    "family": shot.get("ab_family"),
                    "clip": clip,
                    "rep_keys": list(rep.keys())[:12],
                }
            )
            print(f"[{stamp()}]   ok={ok} clip={clip}", flush=True)
        except Exception as exc:  # noqa: BLE001
            # still salvage take if generate wrote file before register/raise
            takes = sorted((ROOT / "takes" / sid).glob(f"*{SEED}*.mp4"))
            if takes:
                burns.append(
                    {
                        "shot_id": sid,
                        "ok": True,
                        "salvaged": True,
                        "dialect": shot.get("ab_dialect"),
                        "family": shot.get("ab_family"),
                        "clip": str(takes[-1]),
                        "error": str(exc)[:200],
                    }
                )
                print(f"[{stamp()}]   salvage clip={takes[-1]} ({exc})", flush=True)
            else:
                burns.append(
                    {
                        "shot_id": sid,
                        "ok": False,
                        "error": str(exc)[:400],
                        "dialect": shot.get("ab_dialect"),
                        "family": shot.get("ab_family"),
                    }
                )
                print(f"[{stamp()}]   FAIL {exc}", flush=True)
        # free VRAM between burns so next capacity check passes (idle only)
        try:
            import urllib.request

            q2 = queue()
            if q2.get("idle"):
                req = urllib.request.Request(
                    f"{COMFY}/free",
                    data=json.dumps(
                        {"unload_models": True, "free_memory": True}
                    ).encode(),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                urllib.request.urlopen(req, timeout=90).read()
                print(f"[{stamp()}]   free-memory between burns", flush=True)
                import time as _t

                _t.sleep(4)
        except Exception as free_exc:  # noqa: BLE001
            print(f"[{stamp()}]   free skip: {free_exc}", flush=True)

    # score pairs
    pairs: dict[str, dict] = {}
    for b in burns:
        fam = str(b.get("family") or "unknown")
        dia = str(b.get("dialect") or "?")
        clip = Path(str(b.get("clip") or ""))
        m = measure(clip) if b.get("ok") and clip.is_file() else {"mean": None, "error": "no_clip"}
        pairs.setdefault(fam, {})[dia] = {
            "shot_id": b.get("shot_id"),
            "ok": b.get("ok"),
            "clip": str(clip) if clip else None,
            "mean": m.get("mean"),
            "size": m.get("size"),
            "error": m.get("error") or b.get("error"),
        }

    score_rows = {}
    flip_votes: list[str] = []
    for fam, sides in pairs.items():
        leg = (sides.get("legacy") or {}).get("mean")
        off = (sides.get("official") or {}).get("mean")
        w = winner(
            float(leg) if leg is not None else None,
            float(off) if off is not None else None,
        )
        score_rows[fam] = {
            "legacy_mean": leg,
            "official_mean": off,
            "motion_mean_winner": w,
            "delta_official_minus_legacy": (
                None
                if leg is None or off is None
                else round(float(off) - float(leg), 4)
            ),
        }
        if fam == "high_motion" and w == "official":
            flip_votes.append("high_motion_official_beats_legacy")
        if fam == "soft_portrait" and w == "official":
            flip_votes.append("soft_portrait_official_beats_legacy")
        if fam == "dialogue_cu" and w in {"official", "tie"}:
            flip_votes.append("dialogue_official_ok_on_mean")

    # Policy: only recommend high flip when official wins by >1.0 mean AND all burns ok
    all_ok = all(b.get("ok") for b in burns) and len(burns) == 6
    high_w = (score_rows.get("high_motion") or {}).get("motion_mean_winner")
    high_delta = (score_rows.get("high_motion") or {}).get("delta_official_minus_legacy") or 0
    default_flip_ready = bool(
        all_ok and high_w == "official" and float(high_delta) >= 1.0
    )

    report = {
        "status": "DONE" if all_ok else "PARTIAL",
        "ok": all_ok,
        "kind": "h3-official-p35-canary",
        "plugin": "2.40.94",
        "seed": SEED,
        "at": stamp(),
        "eval_root": str(ROOT),
        "queue_start": q0,
        "queue_end": queue(),
        "vram_start": v0,
        "vram_end": vram(),
        "compile_rows": compile_rows,
        "burns": burns,
        "pairs": pairs,
        "score": score_rows,
        "policy": {
            "default_dialect": "auto",
            "dialogue": "official",
            "high_motion": "official" if default_flip_ready else "legacy",
            "else": "official",
            "default_flip_ready": default_flip_ready,
            "high_motion_official_env": "AIFILM_H3_HIGH_MOTION_OFFICIAL=1",
            "flip_votes": flip_votes,
            "note": (
                "Flip high default only when machine mean clearly wins; "
                "human lip/identity review still required for dialogue ship."
            ),
        },
        "o3_baseline": str(SKILL / "artifacts" / "2026-08-07-h3-official-ab-canary.json"),
        "live_high_prior": str(SKILL / "artifacts" / "2026-08-07-h3-official-live-canary.json"),
    }

    (ROOT / "receipts" / "h3-official-p35-canary.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (SKILL / "artifacts" / "2026-08-07-h3-official-p35-canary.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"ok": all_ok, "score": score_rows, "policy": report["policy"]}, indent=2), flush=True)
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

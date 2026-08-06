#!/usr/bin/env python3
"""BGM anti-fatigue for long plates (P1 quality · 2026-08-06).

Detects single-loop / same-seed monotony risk and recommends multi-chapter
or pure-instrumental procedural beds. Pure analysis — does not render audio.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from util import read_json, utc_now, write_json

RECEIPT = "bgm-anti-fatigue.json"
LONG_FORM_SEC = 90.0  # soft threshold
VERY_LONG_SEC = 180.0


def check_bgm_anti_fatigue(
    root: Path | str,
    *,
    total_dur_sec: float | None = None,
    music_seed: int | None = None,
    bed_source: str | None = None,
    template_mode: str | None = None,
    mood: str | None = None,
    write: bool = True,
) -> dict[str, Any]:
    base = Path(root).expanduser().resolve()
    spec = read_json(base / "film-spec.json") or {}
    issues: list[dict[str, Any]] = []

    if total_dur_sec is None:
        # Prefer film-spec target or sum of shot durations
        try:
            total_dur_sec = float(spec.get("target_duration") or 0) or None
        except (TypeError, ValueError):
            total_dur_sec = None
        if not total_dur_sec:
            acc = 0.0
            for sc in spec.get("scenes") or []:
                if not isinstance(sc, dict):
                    continue
                for sh in sc.get("shots") or []:
                    if isinstance(sh, dict):
                        try:
                            acc += float(sh.get("duration_sec") or 0)
                        except (TypeError, ValueError):
                            pass
            total_dur_sec = acc or 0.0

    dur = float(total_dur_sec or 0.0)
    bed = (bed_source or "").strip().lower()
    tmpl = (template_mode or "").strip().lower()
    mood_s = (mood or str(spec.get("music_mood") or "rnb")).strip().lower()

    # Long plate + single procedural seed + auto bed → fatigue risk
    if dur >= LONG_FORM_SEC and tmpl in {"", "auto", "procedural", "none"}:
        if bed in {"", "auto", "procedural", "unknown"}:
            issues.append(
                {
                    "code": "BGM_SINGLE_LOOP_RISK",
                    "severity": "soft" if dur < VERY_LONG_SEC else "hard",
                    "message": (
                        f"duration={dur:.0f}s with bed={bed or 'auto'}/template={tmpl or 'auto'} "
                        "risks one-loop fatigue — use music_template=timeline or multi-chapter "
                        "procedural / pure instrumental bed"
                    ),
                }
            )
    if dur >= VERY_LONG_SEC and music_seed is not None and tmpl in {"", "auto"}:
        issues.append(
            {
                "code": "BGM_SEED_MONOTONE",
                "severity": "soft",
                "message": (
                    f"very long plate ({dur:.0f}s) with fixed music_seed={music_seed} — "
                    "prefer chapter motif_seed rotation or approved_library timeline"
                ),
            }
        )
    # Vocal BGM mood on long adult max → prefer pure instrumental
    heat = str(spec.get("heat_scale") or "").strip().lower()
    if heat == "max" and dur >= LONG_FORM_SEC and mood_s in {"pop", "vocal", "lyric"}:
        issues.append(
            {
                "code": "BGM_PREFER_INSTRUMENTAL",
                "severity": "soft",
                "message": "adult max long plate: prefer pure instrumental rnb/bed (no vocal competition)",
            }
        )

    hard = [i for i in issues if i.get("severity") == "hard"]
    ok = not hard
    out: dict[str, Any] = {
        "schema_version": 1,
        "kind": "bgm-anti-fatigue",
        "at": utc_now(),
        "root": str(base),
        "ok": ok,
        "total_dur_sec": dur,
        "music_seed": music_seed,
        "bed_source": bed,
        "template_mode": tmpl,
        "mood": mood_s,
        "issues": issues,
        "recommend": (
            "music_template=timeline or multi-style procedural chapters; pure instrumental default"
            if issues
            else "ok"
        ),
        "next_cmd": (
            None
            if ok
            else f'aifilm final --root "{base}" --music-mood rnb  # or music_template=timeline'
        ),
    }
    if write:
        rec = base / "receipts" / RECEIPT
        rec.parent.mkdir(parents=True, exist_ok=True)
        write_json(rec, out)
    return out

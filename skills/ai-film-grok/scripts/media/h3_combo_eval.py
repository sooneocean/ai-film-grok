#!/usr/bin/env python3
"""Idle-gated H3 T2V/I2V/R2V(/FLF) param+prompt combo evaluation.

Pure matrix + scorer are unit-testable without Comfy. GPU I/O goes only through
shipped run_h3_shot / submission_capacity / free_memory.

Lanes: hero_identity_lock · high_motion_energy · dialogue_mouth_energy · faceless_env
"""
from __future__ import annotations

import json
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

DEFAULT_SEED = 20260805
DEFAULT_STEPS = 20
VERDICT_KIND = "h3-combo-verdict"

PROMPT_FAMILIES: dict[str, dict[str, Any]] = {
    "soft_portrait": {
        "lane_tags": ["hero_identity_lock"],
        "shot_role": "hero",
        "heat_phase": "setup",
        "wardrobe_state": "clothed",
        "prompt_tier": "soft",
        "nar": "soft natural portrait, subtle breathing and gentle head turn, warm indoor light",
        "dsl": {
            "action": "subject holds eye contact with slight smile",
            "motion": "slow push-in, hair micro-motion",
            "visible_change": "expression softens, shoulders rise with breath",
        },
        "author_prompt": (
            "Vertical 9:16 cinematic portrait. Keep the exact same person identity, face, hair, "
            "wardrobe, and lighting from the start frame. Soft indoor ambience. Subtle natural "
            "motion only: gentle breathing, tiny head turn toward camera, soft eye blink, hair "
            "micro-movement. Medium slow push-in. No morphing, no face swap, no extra people, "
            "no text, no logo. Audio: quiet room tone and soft fabric foley; no speech."
        ),
    },
    "high_motion": {
        "lane_tags": ["high_motion_energy", "hero_identity_lock"],
        "shot_role": "hero",
        "heat_phase": "act",
        "wardrobe_state": "clothed",
        "prompt_tier": "high",
        "nar": "high energy body motion, strong physical performance",
        "dsl": {
            "action": "body rocks with vigorous rhythm, hands grip fabric, weight shifts hard",
            "motion": "aggressive handheld push-in and lateral drift, hair and clothes whip",
            "visible_change": "pose changes clearly every second, large motion amplitude",
        },
        "author_prompt": (
            "Vertical 9:16. Animate the start frame with medium cel-anime style lock. "
            "Keep identity and wardrobe fixed. HIGH MOTION priority: large visible pose/body "
            "change every second; avoid frozen portrait or micro-breath-only. Body rocks with "
            "vigorous rhythm, hands grip fabric, weight shifts hard. Aggressive handheld "
            "push-in and lateral drift; hair and clothes whip. Pose changes clearly every "
            "second with large motion amplitude. No morphing, no face swap, no extra people."
        ),
    },
    "dialogue_mandarin": {
        "lane_tags": ["dialogue_mouth_energy", "hero_identity_lock"],
        "shot_role": "hero",
        "heat_phase": "act",
        "wardrobe_state": "clothed",
        "prompt_tier": "medium",
        "screen_mode": "on_camera",
        "shot_size": "cu",
        "nar": "close-up speaking performance",
        "dsl": {
            "action": "character faces camera and speaks clearly",
            "motion": "subtle head motion while talking, mouth articulates",
            "visible_change": "lips form Mandarin syllables, expression engages",
        },
        "audio_cues": [
            {
                "kind": "voice",
                "line_type": "dialogue",
                "speaker": "hero",
                "spoken_text": "过来，靠近一点，别停。",
                "screen_mode": "on_camera",
            }
        ],
        "author_prompt": (
            "Vertical 9:16 close-up. Animate the start frame; keep identity fixed. "
            "Character faces camera and speaks clearly with visible lip sync priority; "
            "mouth articulates Mandarin syllables. line: 「过来，靠近一点，别停。」 "
            "Subtle head motion while talking; expression engages. No morphing, no face swap."
        ),
    },
    "env_no_face": {
        "lane_tags": ["faceless_env"],
        "shot_role": "env",
        "heat_phase": "setup",
        "wardrobe_state": "clothed",
        "prompt_tier": "medium",
        "nar": "empty environment atmosphere plate, no people",
        "dsl": {
            "action": "wind moves curtains and foliage, light shifts on walls",
            "motion": "slow lateral drift across empty room",
            "visible_change": "shadows and fabric move; no faces appear",
        },
        "author_prompt": (
            "Vertical 9:16 text-to-video plate. Empty interior environment, no people, "
            "no faces, no character. Soft window light, curtains and foliage micro-motion, "
            "slow camera drift. Cinematic atmosphere only. No text, no logo."
        ),
    },
}

DEFAULT_COMBO_ORDER: list[dict[str, Any]] = [
    {"combo_id": "soft_i2v", "mode": "i2v", "family": "soft_portrait", "shot_id": "s_soft"},
    {"combo_id": "soft_r2v", "mode": "r2v", "family": "soft_portrait", "shot_id": "s_soft"},
    {"combo_id": "high_i2v", "mode": "i2v", "family": "high_motion", "shot_id": "s_hi"},
    {"combo_id": "high_r2v", "mode": "r2v", "family": "high_motion", "shot_id": "s_hi"},
    {"combo_id": "dlg_i2v", "mode": "i2v", "family": "dialogue_mandarin", "shot_id": "s_dlg"},
    {"combo_id": "dlg_r2v", "mode": "r2v", "family": "dialogue_mandarin", "shot_id": "s_dlg"},
    {"combo_id": "env_t2v", "mode": "t2v", "family": "env_no_face", "shot_id": "s_env"},
    {
        "combo_id": "high_flf",
        "mode": "flf",
        "family": "high_motion",
        "shot_id": "s_hi",
        "requires_last": True,
    },
]


@dataclass
class ComboSpec:
    combo_id: str
    mode: str
    family: str
    shot_id: str
    seed: int = DEFAULT_SEED
    steps: int | str = DEFAULT_STEPS
    requires_last: bool = False
    lane_tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_combo_matrix(
    *,
    seed: int = DEFAULT_SEED,
    include_flf: bool = True,
    order: list[dict[str, Any]] | None = None,
) -> list[ComboSpec]:
    rows = order if order is not None else list(DEFAULT_COMBO_ORDER)
    out: list[ComboSpec] = []
    for raw in rows:
        mode = str(raw["mode"]).lower()
        family = str(raw["family"])
        if not include_flf and mode == "flf":
            continue
        fam = PROMPT_FAMILIES.get(family) or {}
        tags = list(raw.get("lane_tags") or fam.get("lane_tags") or [])
        out.append(
            ComboSpec(
                combo_id=str(raw["combo_id"]),
                mode=mode,
                family=family,
                shot_id=str(raw.get("shot_id") or f"s_{raw['combo_id']}"),
                seed=int(raw.get("seed") or seed),
                steps=raw.get("steps", DEFAULT_STEPS),
                requires_last=bool(raw.get("requires_last")),
                lane_tags=tags,
            )
        )
    return out


def shot_dict_for_family(family: str, shot_id: str) -> dict[str, Any]:
    fam = PROMPT_FAMILIES[family]
    shot: dict[str, Any] = {
        "id": shot_id,
        "shot_role": fam.get("shot_role", "hero"),
        "heat_phase": fam.get("heat_phase", "setup"),
        "wardrobe_state": fam.get("wardrobe_state", "clothed"),
        "nar": fam.get("nar", ""),
        "dsl": dict(fam.get("dsl") or {}),
    }
    if fam.get("screen_mode"):
        shot["screen_mode"] = fam["screen_mode"]
    if fam.get("shot_size"):
        shot["shot_size"] = fam["shot_size"]
    if fam.get("prompt_tier"):
        shot["prompt_tier"] = fam["prompt_tier"]
        shot.setdefault("dsl", {})["prompt_tier"] = fam["prompt_tier"]
    if fam.get("audio_cues"):
        shot["audio_cues"] = list(fam["audio_cues"])
    return shot


def build_eval_film_spec(combos: list[ComboSpec] | None = None) -> dict[str, Any]:
    combos = combos or build_combo_matrix()
    shots_by_id: dict[str, dict[str, Any]] = {}
    for c in combos:
        if c.shot_id not in shots_by_id:
            shots_by_id[c.shot_id] = shot_dict_for_family(c.family, c.shot_id)
    return {
        "title": "h3-combo-eval",
        "genre": "adult",
        "aspect_ratio": "9:16",
        "vo_mode": "storyteller",
        "tts_backend": "edge",
        "i2v_provider": "auto",
        "_i2v_profile": "h3_primary",
        "h3": {
            "enabled": True,
            "stage": "pilot",
            "max_duration_sec": 5,
            "megapixels_draft": 0.2,
            "audio_policy": "prefer_native",
            "allow_bulk": False,
        },
        "scenes": [{"id": "sc_combo", "shots": list(shots_by_id.values())}],
    }


def score_combo_row(row: dict[str, Any]) -> dict[str, float]:
    motion = float(row.get("motion_mean_absdiff") or row.get("motion_mean") or 0.0)
    ident = row.get("identity") if isinstance(row.get("identity"), dict) else {}
    start_l1 = ident.get("start_l1")
    mid_l1 = ident.get("mid_l1")
    end_l1 = ident.get("end_l1")
    mouth = float(row.get("mouth_region_std_change") or 0.0)
    if start_l1 is None:
        identity_score = 0.0
    else:
        s = float(start_l1)
        m = float(mid_l1) if mid_l1 is not None else s
        e = float(end_l1) if end_l1 is not None else m
        penalty = 0.5 * s + 0.3 * m + 0.2 * e
        identity_score = max(0.0, 100.0 - penalty)
    return {
        "identity_score": round(identity_score, 4),
        "motion_score": round(motion, 4),
        "mouth_score": round(mouth, 4),
        "hero_balanced": round(identity_score * 0.7 + min(motion, 40.0) * 0.3, 4),
    }


def rank_lanes(
    rows: list[dict[str, Any]],
    *,
    identity_start_max: float = 45.0,
) -> dict[str, Any]:
    enriched: list[dict[str, Any]] = []
    for r in rows:
        if not r.get("ok", True):
            continue
        enriched.append({**r, "scores": score_combo_row(r)})

    def _pick(cands: list[dict[str, Any]], key: Callable[[dict[str, Any]], float]) -> dict[str, Any] | None:
        if not cands:
            return None
        best = max(cands, key=key)
        return {
            "combo_id": best.get("combo_id"),
            "mode": best.get("mode"),
            "family": best.get("family"),
            "score": key(best),
            "scores": best.get("scores"),
            "motion_mean_absdiff": best.get("motion_mean_absdiff") or best.get("motion_mean"),
            "identity": best.get("identity"),
            "mouth_region_std_change": best.get("mouth_region_std_change"),
        }

    def _has_tag(r: dict[str, Any], tag: str) -> bool:
        tags = list(r.get("lane_tags") or [])
        fam_tags = {
            "soft_portrait": ["hero_identity_lock"],
            "high_motion": ["high_motion_energy", "hero_identity_lock"],
            "dialogue_mandarin": ["dialogue_mouth_energy", "hero_identity_lock"],
            "env_no_face": ["faceless_env"],
        }.get(str(r.get("family")), [])
        return tag in tags or tag in fam_tags

    id_cands = [
        r for r in enriched
        if r.get("mode") in {"i2v", "r2v", "flf"}
        and (_has_tag(r, "hero_identity_lock") or r.get("family") in {"soft_portrait", "high_motion", "dialogue_mandarin"})
        and isinstance(r.get("identity"), dict)
        and r["identity"].get("start_l1") is not None
    ]
    id_soft = [r for r in id_cands if r.get("family") == "soft_portrait"]
    hero = _pick(id_soft or id_cands, lambda r: float(r["scores"]["identity_score"]))

    hi_cands = [r for r in enriched if r.get("family") == "high_motion" or _has_tag(r, "high_motion_energy")]
    hi_locked = [
        r for r in hi_cands
        if not isinstance(r.get("identity"), dict)
        or r["identity"].get("start_l1") is None
        or float(r["identity"]["start_l1"]) <= identity_start_max
    ]
    high = _pick(hi_locked or hi_cands, lambda r: float(r["scores"]["motion_score"]))

    dlg_cands = [r for r in enriched if r.get("family") == "dialogue_mandarin" or _has_tag(r, "dialogue_mouth_energy")]
    dlg_locked = [
        r for r in dlg_cands
        if not isinstance(r.get("identity"), dict)
        or r["identity"].get("start_l1") is None
        or float(r["identity"]["start_l1"]) <= identity_start_max
    ]
    dialogue = _pick(
        dlg_locked or dlg_cands,
        lambda r: float(r["scores"]["mouth_score"]) * 2.0 + float(r["scores"]["identity_score"]) * 0.05,
    )

    env_cands = [
        r for r in enriched
        if r.get("mode") == "t2v" or r.get("family") == "env_no_face" or _has_tag(r, "faceless_env")
    ]
    env_true = [
        r for r in env_cands
        if not isinstance(r.get("identity"), dict)
        or r["identity"].get("start_l1") is None
        or r["identity"].get("note")
    ]
    if env_true and any((r.get("motion_mean_absdiff") or r.get("motion_mean")) is not None for r in env_true):
        faceless = _pick(env_true, lambda r: float(r["scores"]["motion_score"]))
    else:
        faceless = {
            "combo_id": "env_t2v_policy", "mode": "t2v", "family": "env_no_face",
            "score": None, "score_basis": "policy_only",
            "motion_mean_absdiff": None,
            "identity": {"start_l1": None, "note": "N/A policy_only"},
        }

    winners = {
        "hero_identity_lock": hero,
        "high_motion_energy": high,
        "dialogue_mouth_energy": dialogue,
        "faceless_env": faceless,
    }
    recipes: dict[str, Any] = {}
    for lane, w in winners.items():
        if not w:
            continue
        recipes[lane] = {
            "mode": w["mode"],
            "prompt_family": w["family"],
            "combo_id": w["combo_id"],
            "steps": DEFAULT_STEPS,
            "seed_policy": "fixed_for_ab_or_shot_seed",
            "score": w["score"],
        }
    return {
        "schema_version": 1,
        "kind": VERDICT_KIND,
        "ts": datetime.now(timezone.utc).isoformat(),
        "winners": winners,
        "recipes": recipes,
        "rows_scored": len(enriched),
        "lanes_complete": [k for k, v in winners.items() if v is not None],
    }


def merge_winners_into_effect_defaults(verdict: dict[str, Any]) -> dict[str, Any]:
    recipes = verdict.get("recipes") if isinstance(verdict.get("recipes"), dict) else {}
    winners = verdict.get("winners") if isinstance(verdict.get("winners"), dict) else {}
    return {
        "schema_version": 1,
        "kind": "h3-combo-winners",
        "policy": "h3_max_effect_combo_v1",
        "source_verdict_kind": VERDICT_KIND,
        "ts": verdict.get("ts") or datetime.now(timezone.utc).isoformat(),
        "lanes": {
            "hero_identity_lock": {
                "preferred_mode": (recipes.get("hero_identity_lock") or {}).get("mode", "i2v"),
                "prompt_family": (recipes.get("hero_identity_lock") or {}).get("prompt_family", "soft_portrait"),
                "notes": "Lock face from approved still; soft portrait control wins identity L1",
                "winner": winners.get("hero_identity_lock"),
            },
            "high_motion_energy": {
                "preferred_mode": (recipes.get("high_motion_energy") or {}).get("mode", "r2v"),
                "prompt_family": (recipes.get("high_motion_energy") or {}).get("prompt_family", "high_motion"),
                "notes": "HIGH MOTION clause required; R2V when energy > identity; I2V first if identity lock still required",
                "winner": winners.get("high_motion_energy"),
            },
            "dialogue_mouth_energy": {
                "preferred_mode": (recipes.get("dialogue_mouth_energy") or {}).get("mode", "i2v"),
                "prompt_family": (recipes.get("dialogue_mouth_energy") or {}).get("prompt_family", "dialogue_mandarin"),
                "notes": "Default I2V + Mandarin line inject; R2V only for extreme mouth CU when identity can float",
                "winner": winners.get("dialogue_mouth_energy"),
            },
            "faceless_env": {
                "preferred_mode": (recipes.get("faceless_env") or {}).get("mode", "t2v"),
                "prompt_family": (recipes.get("faceless_env") or {}).get("prompt_family", "env_no_face"),
                "notes": "Never hang cast face on T2V; env/bridge only",
                "winner": winners.get("faceless_env"),
            },
        },
        "weapon_defaults": {
            "steps": DEFAULT_STEPS,
            "duration_sec": 5.0,
            "fps": 24,
            "note": "registry tuning.steps.allowed is [20] only",
        },
    }


def probe_capacity(base_url: str | None = None) -> dict[str, Any]:
    from comfy_armory import default_base_url
    from comfy_video import submission_capacity

    return submission_capacity(base_url or default_base_url())


def wait_until_idle(
    *,
    base_url: str | None = None,
    poll_sec: float = 15.0,
    max_wait_sec: float = 3600.0,
    log: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    _log = log or (lambda _m: None)
    deadline = time.time() + max_wait_sec
    last: dict[str, Any] = {}
    while time.time() < deadline:
        last = probe_capacity(base_url)
        if last.get("ok") and str(last.get("status") or "") == "ready":
            _log("capacity ready")
            return last
        blockers = last.get("blockers") or []
        codes = [b.get("code") for b in blockers if isinstance(b, dict)]
        _log(f"capacity busy status={last.get('status')} blockers={codes}; sleep {poll_sec}s")
        time.sleep(poll_sec)
    last = last or probe_capacity(base_url)
    last["wait_timeout"] = True
    return last


def _ffmpeg_frame(video: Path, t_sec: float, out: Path) -> bool:
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-y", "-ss", f"{t_sec:.3f}", "-i", str(video), "-frames:v", "1", "-q:v", "2", str(out)]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=60)
        return proc.returncode == 0 and out.is_file()
    except (OSError, subprocess.TimeoutExpired):
        return False


def _l1_gray(path_a: Path, path_b: Path, size: tuple[int, int] = (140, 248)) -> float | None:
    w, h = size

    def _raw(p: Path) -> bytes | None:
        cmd = [
            "ffmpeg", "-y", "-i", str(p), "-vf", f"scale={w}:{h},format=gray",
            "-f", "rawvideo", "-pix_fmt", "gray", "pipe:1",
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, timeout=60)
        except (OSError, subprocess.TimeoutExpired):
            return None
        need = w * h
        if proc.returncode != 0 or len(proc.stdout) < need:
            return None
        return proc.stdout[:need]

    a, b = _raw(path_a), _raw(path_b)
    if not a or not b:
        return None
    return round(sum(abs(a[i] - b[i]) for i in range(len(a))) / float(len(a)), 4)


def _mouth_std_change(video: Path, work: Path) -> float | None:
    frames: list[Path] = []
    for i, t in enumerate((0.5, 1.5, 2.5, 3.5, 4.5)):
        fp = work / f"mouth_{i}.jpg"
        if _ffmpeg_frame(video, t, fp):
            frames.append(fp)
    if len(frames) < 2:
        return None
    w, h = 80, 48

    def _mouth_raw(p: Path) -> bytes | None:
        vf = f"scale=160:284,crop={w}:{h}:(160-{w})/2:284-{h}-20,format=gray"
        cmd = ["ffmpeg", "-y", "-i", str(p), "-vf", vf, "-f", "rawvideo", "-pix_fmt", "gray", "pipe:1"]
        try:
            proc = subprocess.run(cmd, capture_output=True, timeout=60)
        except (OSError, subprocess.TimeoutExpired):
            return None
        need = w * h
        if proc.returncode != 0 or len(proc.stdout) < need:
            return None
        return proc.stdout[:need]

    raws = [r for r in (_mouth_raw(f) for f in frames) if r]
    if len(raws) < 2:
        return None
    diffs: list[float] = []
    prev = raws[0]
    for cur in raws[1:]:
        diffs.append(sum(abs(cur[i] - prev[i]) for i in range(len(cur))) / float(len(cur)))
        prev = cur
    mean = sum(diffs) / len(diffs)
    var = sum((d - mean) ** 2 for d in diffs) / len(diffs)
    return round(mean + (var ** 0.5), 4)


def measure_clip_metrics(
    video: Path, *, still: Path | None, work_dir: Path, faceless: bool = False,
) -> dict[str, Any]:
    from i2v_motion_gate import measure_mean_absdiff

    work_dir.mkdir(parents=True, exist_ok=True)
    mean = measure_mean_absdiff(video)
    dur = 5.0
    try:
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(video)],
            capture_output=True, text=True, timeout=30,
        )
        if probe.returncode == 0 and probe.stdout.strip():
            dur = max(0.5, float(probe.stdout.strip()))
    except (OSError, subprocess.TimeoutExpired, ValueError):
        pass
    t_start, t_mid, t_end = 0.05, dur * 0.5, max(0.1, dur - 0.15)
    start_f, mid_f, end_f = work_dir / "start.jpg", work_dir / "mid.jpg", work_dir / "end.jpg"
    _ffmpeg_frame(video, t_start, start_f)
    _ffmpeg_frame(video, t_mid, mid_f)
    _ffmpeg_frame(video, t_end, end_f)
    if faceless or still is None or not still.is_file():
        identity: dict[str, Any] = {
            "start_l1": None, "mid_l1": None, "end_l1": None, "note": "N/A faceless or no still",
        }
    else:
        identity = {
            "start_l1": _l1_gray(still, start_f) if start_f.is_file() else None,
            "mid_l1": _l1_gray(still, mid_f) if mid_f.is_file() else None,
            "end_l1": _l1_gray(still, end_f) if end_f.is_file() else None,
        }
    mouth = _mouth_std_change(video, work_dir / "mouth") if not faceless else None
    return {
        "motion_mean_absdiff": mean,
        "motion_mean": mean,
        "identity": identity,
        "mouth_region_std_change": mouth,
        "size_bytes": video.stat().st_size if video.is_file() else 0,
        "duration_sec": dur,
        "frames": {
            "start": str(start_f) if start_f.is_file() else None,
            "mid": str(mid_f) if mid_f.is_file() else None,
            "end": str(end_f) if end_f.is_file() else None,
        },
    }


def prepare_eval_root(
    eval_root: Path | str,
    *,
    source_still: Path | str | None = None,
    end_still: Path | str | None = None,
    combos: list[ComboSpec] | None = None,
) -> Path:
    root = Path(eval_root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    combos = combos or build_combo_matrix()
    (root / "film-spec.json").write_text(
        json.dumps(build_eval_film_spec(combos), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    stills = root / "stills"
    stills.mkdir(exist_ok=True)
    prompts = root / "receipts" / "prompts"
    prompts.mkdir(parents=True, exist_ok=True)
    for d in ("takes", "receipts", "compare"):
        (root / d).mkdir(exist_ok=True)
    src = Path(source_still).expanduser().resolve() if source_still else None
    end = Path(end_still).expanduser().resolve() if end_still else None
    seen: set[str] = set()
    for c in combos:
        if c.shot_id in seen:
            continue
        seen.add(c.shot_id)
        fam = PROMPT_FAMILIES[c.family]
        (prompts / f"{c.shot_id}.i2v.txt").write_text(
            str(fam.get("author_prompt") or "") + "\n", encoding="utf-8"
        )
        if c.mode != "t2v" and c.family != "env_no_face":
            dest = stills / f"{c.shot_id}.png"
            if src and src.is_file() and not dest.is_file():
                shutil.copy2(src, dest)
            if c.requires_last or c.mode == "flf":
                end_dest = stills / f"{c.shot_id}_end.png"
                if end and end.is_file() and not end_dest.is_file():
                    shutil.copy2(end, end_dest)
    (root / "compare" / "combo-matrix.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "kind": "h3-combo-matrix",
                "seed": DEFAULT_SEED,
                "steps": DEFAULT_STEPS,
                "combos": [c.to_dict() for c in combos],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return root


def run_combo_grid(
    eval_root: Path | str,
    *,
    combos: list[ComboSpec] | None = None,
    base_url: str | None = None,
    poll_sec: float = 20.0,
    max_wait_per_job_sec: float = 3600.0,
    free_memory_on_mode_switch: bool = True,
    execute: bool = True,
    scratch_dir: Path | str | None = None,
    log: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    from util import write_json

    root = Path(eval_root).expanduser().resolve()
    combos = combos or build_combo_matrix()
    _log = log or (lambda m: print(m, flush=True))
    scratch = Path(scratch_dir).expanduser().resolve() if scratch_dir else None
    if scratch:
        (scratch / "combo-runs").mkdir(parents=True, exist_ok=True)
    compare = root / "compare"
    compare.mkdir(exist_ok=True)
    rows: list[dict[str, Any]] = []
    last_mode: str | None = None
    capacity_log: list[dict[str, Any]] = []

    if not execute:
        plan = {"ok": True, "dry_run": True, "combos": [c.to_dict() for c in combos], "eval_root": str(root)}
        write_json(compare / "dry-plan.json", plan)
        return plan

    for c in combos:
        if c.requires_last or c.mode == "flf":
            if not (root / "stills" / f"{c.shot_id}_end.png").is_file():
                row = {
                    "ok": False, "combo_id": c.combo_id, "mode": c.mode, "family": c.family,
                    "shot_id": c.shot_id, "lane_tags": c.lane_tags, "skipped": True, "skip_reason": "no_end_still",
                }
                rows.append(row)
                write_json(compare / f"{c.combo_id}.json", row)
                _log(f"skip {c.combo_id}: no end still")
                continue

        _log(f"wait capacity for {c.combo_id} ({c.mode}/{c.family})…")
        cap = wait_until_idle(base_url=base_url, poll_sec=poll_sec, max_wait_sec=max_wait_per_job_sec, log=_log)
        capacity_log.append({
            "combo_id": c.combo_id,
            "capacity": {"status": cap.get("status"), "blockers": cap.get("blockers"), "ok": cap.get("ok"), "wait_timeout": cap.get("wait_timeout")},
        })
        if not (cap.get("ok") and str(cap.get("status")) == "ready"):
            row = {
                "ok": False, "combo_id": c.combo_id, "mode": c.mode, "family": c.family,
                "shot_id": c.shot_id, "lane_tags": c.lane_tags, "error": "capacity_timeout_or_blocked",
                "capacity": capacity_log[-1]["capacity"],
            }
            rows.append(row)
            write_json(compare / f"{c.combo_id}.json", row)
            continue

        if free_memory_on_mode_switch and last_mode and last_mode != c.mode:
            try:
                from comfy_armory import default_base_url
                from comfy_video import free_memory
                _log(f"free-memory on mode switch {last_mode}→{c.mode}")
                free_memory(base_url or default_base_url())
                time.sleep(3)
            except Exception as exc:  # noqa: BLE001
                _log(f"free-memory warning: {exc}")

        prompt_text = ""
        pfile = root / "receipts" / "prompts" / f"{c.shot_id}.i2v.txt"
        if pfile.is_file():
            prompt_text = pfile.read_text(encoding="utf-8").strip()
        still_path = root / "stills" / f"{c.shot_id}.png"
        still_for_run = still_path if still_path.is_file() else None
        last_path = root / "stills" / f"{c.shot_id}_end.png"
        last_for_run = last_path if last_path.is_file() else None

        _log(f"run {c.combo_id}: mode={c.mode} seed={c.seed}")
        try:
            from h3_workflow import run_h3_shot
            run_receipt = run_h3_shot(
                root, c.shot_id, mode=c.mode, register=False, seed=c.seed,
                timeout_sec=1800, enqueue_queue=False, production_stage="pilot",
                allow_experimental=True, still_override=still_for_run,
                last_override=last_for_run if c.mode == "flf" else None,
            )
        except Exception as exc:  # noqa: BLE001
            row = {
                "ok": False, "combo_id": c.combo_id, "mode": c.mode, "family": c.family,
                "shot_id": c.shot_id, "lane_tags": c.lane_tags, "seed": c.seed,
                "steps": c.steps if isinstance(c.steps, int) else "weapon_default",
                "prompt_text": prompt_text, "still_path": str(still_for_run) if still_for_run else None,
                "error": str(exc),
            }
            rows.append(row)
            write_json(compare / f"{c.combo_id}.json", row)
            if scratch:
                write_json(scratch / "combo-runs" / f"{c.combo_id}.json", row)
            last_mode = c.mode
            continue

        deliver = Path(str(run_receipt.get("deliver_path") or run_receipt.get("raw_path") or ""))
        faceless = c.mode == "t2v" or c.family == "env_no_face"
        metrics = (
            measure_clip_metrics(
                deliver, still=still_for_run if not faceless else None,
                work_dir=compare / f"_frames_{c.combo_id}", faceless=faceless,
            )
            if deliver.is_file()
            else {"error": "no_deliver_path", "motion_mean_absdiff": None}
        )
        spine = root / "receipts" / "prompts" / f"{c.shot_id}.h3.spine.txt"
        if spine.is_file():
            prompt_text = spine.read_text(encoding="utf-8").strip() or prompt_text
        row = {
            "ok": bool(run_receipt.get("ok", True)) and deliver.is_file(),
            "combo_id": c.combo_id, "mode": c.mode, "family": c.family, "shot_id": c.shot_id,
            "lane_tags": c.lane_tags, "seed": c.seed,
            "steps": c.steps if isinstance(c.steps, int) else "weapon_default",
            "prompt_text": prompt_text,
            "still_path": str(still_for_run) if still_for_run else None,
            "last_path": str(last_for_run) if last_for_run else None,
            "deliver_path": str(deliver) if deliver.is_file() else None,
            "run_receipt": {k: run_receipt.get(k) for k in ("ok", "weapon_id", "source_endpoint", "raw_path", "deliver_path", "receipt")},
            "motion_mean_absdiff": metrics.get("motion_mean_absdiff"),
            "motion_mean": metrics.get("motion_mean"),
            "identity": metrics.get("identity"),
            "mouth_region_std_change": metrics.get("mouth_region_std_change"),
            "size_bytes": metrics.get("size_bytes"),
            "duration_sec": metrics.get("duration_sec"),
            "frame_extracts": metrics.get("frames"),
        }
        rows.append(row)
        write_json(compare / f"{c.combo_id}.json", row)
        if scratch:
            write_json(scratch / "combo-runs" / f"{c.combo_id}.json", row)
        _log(f"done {c.combo_id}: motion={row.get('motion_mean_absdiff')} id_start={(row.get('identity') or {}).get('start_l1')}")
        last_mode = c.mode

    ab_metrics = {
        "schema_version": 1, "kind": "h3-combo-ab-metrics",
        "ts": datetime.now(timezone.utc).isoformat(),
        "seed": DEFAULT_SEED, "steps": DEFAULT_STEPS, "eval_root": str(root),
        "rows": rows, "capacity_log_tail": capacity_log[-5:],
    }
    write_json(compare / "ab-metrics.json", ab_metrics)
    verdict = rank_lanes(rows)
    write_json(compare / "verdict.json", verdict)
    winners_doc = merge_winners_into_effect_defaults(verdict)
    write_json(compare / "winners-merged.json", winners_doc)
    if scratch:
        write_json(scratch / "h3-combo-verdict.json", verdict)
        write_json(scratch / "ab-metrics.json", ab_metrics)
        write_json(scratch / "capacity-log.json", capacity_log)
    return {
        "ok": any(r.get("ok") for r in rows),
        "eval_root": str(root),
        "rows": rows,
        "verdict": verdict,
        "winners": winners_doc,
        "capacity_events": len(capacity_log),
        "lanes_complete": verdict.get("lanes_complete") or [],
    }


def load_combo_winners(path: Path | str | None = None) -> dict[str, Any] | None:
    if path is None:
        here = Path(__file__).resolve().parent.parent
        candidates = [here.parent / "registry" / "h3-combo-winners.json", here / "h3-combo-winners.json"]
    else:
        candidates = [Path(path).expanduser().resolve()]
    for p in candidates:
        if p.is_file():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(data, dict):
                return data
    return None


def winner_tips_from_registry(winners: dict[str, Any] | None = None) -> list[str]:
    data = winners if winners is not None else load_combo_winners()
    if not data:
        return []
    lanes = data.get("lanes") if isinstance(data.get("lanes"), dict) else {}
    tips: list[str] = []
    labels = {
        "hero_identity_lock": "身份锁脸",
        "high_motion_energy": "高动能量",
        "dialogue_mouth_energy": "对白嘴型",
        "faceless_env": "无脸环境",
    }
    for key in ("hero_identity_lock", "high_motion_energy", "dialogue_mouth_energy", "faceless_env"):
        lane = lanes.get(key) if isinstance(lanes.get(key), dict) else None
        if not lane:
            continue
        w = lane.get("winner") if isinstance(lane.get("winner"), dict) else {}
        score = w.get("score")
        score_s = f" score={score}" if score is not None else ""
        tips.append(
            f"combo-win {labels.get(key, key)}: mode={lane.get('preferred_mode') or '?'} "
            f"family={lane.get('prompt_family') or '?'}{score_s}"
        )
    if data.get("weapon_defaults"):
        wd = data["weapon_defaults"]
        tips.append(
            f"combo weapon defaults: steps={wd.get('steps')} duration={wd.get('duration_sec')}s (registry-locked)"
        )
    return tips


def write_winners_registry(winners_doc: dict[str, Any], *, path: Path | str | None = None) -> Path:
    if path is None:
        path = Path(__file__).resolve().parents[2] / "registry" / "h3-combo-winners.json"
    p = Path(path).expanduser().resolve()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(winners_doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return p

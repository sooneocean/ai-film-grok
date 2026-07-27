#!/usr/bin/env python3
"""I2V high-motion product gate (P0 · 2026-07-27).

Pixel kinetic floors (mean_absdiff · fps=5 · 140×248 gray per lesson):
  - normal (non-act/climax): mean ≥ 18
  - meat (act/climax): mean ≥ 20 (target ≥ 24)
  - envelope after 60s / meat window: mean ≥ 18

Ken Burns / micro-breath / weak raw cannot pass as meat or final plate.
Desktop final copy only when receipts/i2v-final-gate.json ok=true.

Pure functions first — measure mean elsewhere (ffmpeg) and feed numbers here.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Product hard floors (hard-defaults + lessons-2026-07-27-high-motion-style-lock-final)
MEAN_NORMAL_FLOOR = 18.0
MEAN_MEAT_FLOOR = 20.0
MEAN_MEAT_TARGET = 24.0
MEAN_ENVELOPE_FLOOR = 18.0

# Sample geometry documented for mean_absdiff (not enforced here; callers may match)
MEAN_ABSDIFF_FPS = 5
MEAN_ABSDIFF_WIDTH = 140
MEAN_ABSDIFF_HEIGHT = 248

MEAT_PHASES = frozenset({"act", "climax"})
MOTION_TIERS = frozenset({"meat", "normal"})

# Source tags that must never count as a passing high-motion take
FORBIDDEN_SOURCE_TAGS = frozenset(
    {
        "ken_burns",
        "kb",
        "kenburns",
        "micro_breath",
        "micro-breath",
        "static_hold",
        "static",
        "slideshow",
        "still_hold",
    }
)

CODE_MEAT_MEAN_LOW = "I2V_MEAT_MEAN_LOW"
CODE_NORMAL_MEAN_LOW = "I2V_NORMAL_MEAN_LOW"
CODE_FORBIDDEN_SOURCE = "I2V_FORBIDDEN_SOURCE"
CODE_ENVELOPE_LOW = "I2V_ENVELOPE_MEAN_LOW"
CODE_RAW_INCOMPLETE = "I2V_RAW_INCOMPLETE"
CODE_KB_FALLBACK = "I2V_KB_FALLBACK_PLATE"
CODE_STYLE_FAIL = "I2V_STYLE_AUDIT_FAIL"


def motion_tier_for_phase(heat_phase: str | None) -> str:
    """Map heat_phase → motion tier (meat for act/climax, else normal)."""
    ph = str(heat_phase or "").strip().lower()
    if ph in MEAT_PHASES:
        return "meat"
    return "normal"


def floor_for_tier(tier: str) -> float:
    t = str(tier or "normal").strip().lower()
    if t == "meat":
        return MEAN_MEAT_FLOOR
    return MEAN_NORMAL_FLOOR


def target_for_tier(tier: str) -> float:
    t = str(tier or "normal").strip().lower()
    if t == "meat":
        return MEAN_MEAT_TARGET
    return MEAN_NORMAL_FLOOR + 2.0  # normal soft target 20


def source_is_forbidden(source: str | None, *, tags: list[str] | None = None) -> bool:
    """True if take is Ken Burns / micro-breath / static pad (cannot pass high-motion)."""
    blob_parts: list[str] = []
    if source:
        blob_parts.append(str(source).strip().lower())
    for t in tags or []:
        blob_parts.append(str(t).strip().lower())
    blob = " ".join(blob_parts)
    if not blob:
        return False
    for bad in FORBIDDEN_SOURCE_TAGS:
        if bad in blob.replace("-", "_") or bad in blob:
            return True
    # common aliases
    if "ken burns" in blob or "ken_burns" in blob:
        return True
    return False


def evaluate_shot_motion(
    mean: float | None,
    *,
    heat_phase: str | None = None,
    tier: str | None = None,
    source: str | None = None,
    source_tags: list[str] | None = None,
    shot_id: str | None = None,
) -> dict[str, Any]:
    """Grade one shot's mean_absdiff against tier floors.

    Returns stable fields: ok, tier, mean, floor, target, codes, issues.
    """
    resolved_tier = (tier or motion_tier_for_phase(heat_phase)).strip().lower()
    if resolved_tier not in MOTION_TIERS:
        resolved_tier = "normal"
    floor = floor_for_tier(resolved_tier)
    target = target_for_tier(resolved_tier)
    codes: list[str] = []
    issues: list[dict[str, Any]] = []
    mean_f: float | None
    try:
        mean_f = float(mean) if mean is not None else None
    except (TypeError, ValueError):
        mean_f = None

    if source_is_forbidden(source, tags=source_tags):
        codes.append(CODE_FORBIDDEN_SOURCE)
        issues.append(
            {
                "code": CODE_FORBIDDEN_SOURCE,
                "severity": "error",
                "message": (
                    f"shot {shot_id or '?'} source={source!r} is Ken Burns/static/micro — "
                    "forbidden as high-motion I2V plate; pick max mean take from raw/boost"
                ),
            }
        )

    if mean_f is None:
        code = CODE_MEAT_MEAN_LOW if resolved_tier == "meat" else CODE_NORMAL_MEAN_LOW
        codes.append(code)
        issues.append(
            {
                "code": code,
                "severity": "error",
                "message": f"shot {shot_id or '?'} missing mean_absdiff (tier={resolved_tier})",
            }
        )
    elif mean_f + 1e-9 < floor:
        code = CODE_MEAT_MEAN_LOW if resolved_tier == "meat" else CODE_NORMAL_MEAN_LOW
        codes.append(code)
        issues.append(
            {
                "code": code,
                "severity": "error",
                "message": (
                    f"shot {shot_id or '?'} mean={mean_f:.2f} < {resolved_tier} floor "
                    f"{floor:.0f} (target {target:.0f}); reshoot high-motion or pick stronger take"
                ),
            }
        )

    ok = len(codes) == 0
    return {
        "ok": ok,
        "id": shot_id,
        "tier": resolved_tier,
        "heat_phase": (str(heat_phase).strip().lower() if heat_phase else None),
        "mean": mean_f,
        "floor": floor,
        "target": target,
        "meets_target": bool(mean_f is not None and mean_f + 1e-9 >= target),
        "source": source,
        "codes": codes,
        "issues": issues,
    }


def build_high_motion_audit(
    shots: list[dict[str, Any]],
    *,
    metric: str = "mean_absdiff",
) -> dict[str, Any]:
    """Build receipts/i2v-high-motion-audit.json payload from per-shot mean rows.

    Each shot dict may include:
      id, heat_phase, tier, mean | mean_absdiff, source, source_tags,
      t_start_sec (for envelope after 60s)
    """
    per_shot: list[dict[str, Any]] = []
    all_codes: list[str] = []
    meat_means: list[float] = []
    normal_means: list[float] = []
    after_60_means: list[float] = []
    for raw in shots:
        if not isinstance(raw, dict):
            continue
        sid = str(raw.get("id") or raw.get("shot_id") or "")
        mean_raw = raw.get("mean")
        if mean_raw is None:
            mean_raw = raw.get("mean_absdiff")
        if mean_raw is None and metric in raw:
            mean_raw = raw.get(metric)
        tags = raw.get("source_tags")
        tag_list = [str(t) for t in tags] if isinstance(tags, (list, tuple)) else None
        row = evaluate_shot_motion(
            mean_raw if mean_raw is None else float(mean_raw),
            heat_phase=raw.get("heat_phase") or raw.get("phase"),
            tier=raw.get("tier"),
            source=str(raw.get("source") or "") or None,
            source_tags=tag_list,
            shot_id=sid or None,
        )
        per_shot.append(row)
        all_codes.extend(row.get("codes") or [])
        m = row.get("mean")
        if isinstance(m, (int, float)):
            if row.get("tier") == "meat":
                meat_means.append(float(m))
            else:
                normal_means.append(float(m))
            t0 = raw.get("t_start_sec")
            try:
                if t0 is not None and float(t0) >= 60.0:
                    after_60_means.append(float(m))
            except (TypeError, ValueError):
                pass

    envelope_ok = True
    if after_60_means:
        env_mean = sum(after_60_means) / len(after_60_means)
        if env_mean + 1e-9 < MEAN_ENVELOPE_FLOOR:
            envelope_ok = False
            all_codes.append(CODE_ENVELOPE_LOW)
    else:
        env_mean = None

    meat_window_ok = True
    meat_window_mean = (sum(meat_means) / len(meat_means)) if meat_means else None
    if meat_means and meat_window_mean is not None:
        if meat_window_mean + 1e-9 < MEAN_ENVELOPE_FLOOR:
            meat_window_ok = False
            all_codes.append(CODE_ENVELOPE_LOW)

    shot_ok = all(bool(r.get("ok")) for r in per_shot) if per_shot else True
    codes = sorted(set(all_codes))
    ok = shot_ok and envelope_ok and meat_window_ok
    return {
        "kind": "i2v-high-motion-audit",
        "ok": ok,
        "metric": metric,
        "floors": {
            "normal": MEAN_NORMAL_FLOOR,
            "meat": MEAN_MEAT_FLOOR,
            "meat_target": MEAN_MEAT_TARGET,
            "envelope": MEAN_ENVELOPE_FLOOR,
        },
        "sample": {
            "fps": MEAN_ABSDIFF_FPS,
            "width": MEAN_ABSDIFF_WIDTH,
            "height": MEAN_ABSDIFF_HEIGHT,
            "format": "gray",
        },
        "per_shot": per_shot,
        "codes": codes,
        "meat_mean_avg": round(meat_window_mean, 3) if meat_window_mean is not None else None,
        "normal_mean_avg": (
            round(sum(normal_means) / len(normal_means), 3) if normal_means else None
        ),
        "envelope_after_60_mean": round(env_mean, 3) if env_mean is not None else None,
        "envelope_ok": envelope_ok,
        "meat_window_ok": meat_window_ok,
        "note": (
            "高动态常态: normal≥18 meat≥20(target≥24); "
            "禁 Ken Burns/微抖/弱 raw 装片; 多 take 取最高 mean 且时长够"
        ),
    }


def build_i2v_final_gate(
    audit: dict[str, Any] | None,
    *,
    raw_complete: bool = True,
    kb_fallback: bool = False,
    style_ok: bool = True,
    shot_count: int | None = None,
    raw_ok_count: int | None = None,
) -> dict[str, Any]:
    """Build receipts/i2v-final-gate.json — desktop film_final only when ok=true.

    Requires high-motion audit ok, full raw (not KB pad), and style audit pass.
    """
    codes: list[str] = []
    issues: list[dict[str, Any]] = []
    audit = audit if isinstance(audit, dict) else {}
    motion_ok = audit.get("ok") is True
    if not motion_ok:
        for c in audit.get("codes") or []:
            codes.append(str(c))
        if not codes:
            codes.append(CODE_NORMAL_MEAN_LOW)
        issues.append(
            {
                "code": "I2V_HIGH_MOTION_AUDIT_FAIL",
                "severity": "error",
                "message": "i2v-high-motion-audit not ok — fix weak meat/normal means before final",
            }
        )

    if kb_fallback:
        codes.append(CODE_KB_FALLBACK)
        issues.append(
            {
                "code": CODE_KB_FALLBACK,
                "severity": "error",
                "message": "plate uses Ken Burns fallback — forbidden for desktop final",
            }
        )

    if not raw_complete:
        codes.append(CODE_RAW_INCOMPLETE)
        issues.append(
            {
                "code": CODE_RAW_INCOMPLETE,
                "severity": "error",
                "message": "I2V raw incomplete — all shots must be real I2V takes, not pads",
            }
        )
    elif shot_count is not None and raw_ok_count is not None:
        if int(raw_ok_count) < int(shot_count):
            codes.append(CODE_RAW_INCOMPLETE)
            issues.append(
                {
                    "code": CODE_RAW_INCOMPLETE,
                    "severity": "error",
                    "message": f"raw ok {raw_ok_count}/{shot_count} — not full I2V plate",
                }
            )

    if not style_ok:
        codes.append(CODE_STYLE_FAIL)
        issues.append(
            {
                "code": CODE_STYLE_FAIL,
                "severity": "error",
                "message": "style audit fail (semi-real drift) — re-I2V from style-locked still + MEDIUM LOCK",
            }
        )

    codes = sorted(set(codes))
    ok = (
        motion_ok
        and not kb_fallback
        and raw_complete
        and style_ok
        and (shot_count is None or raw_ok_count is None or int(raw_ok_count) >= int(shot_count))
    )
    return {
        "kind": "i2v-final-gate",
        "ok": ok,
        "codes": codes,
        "issues": issues,
        "motion_audit_ok": motion_ok,
        "raw_complete": raw_complete,
        "kb_fallback": kb_fallback,
        "style_ok": style_ok,
        "shot_count": shot_count,
        "raw_ok_count": raw_ok_count,
        "floors": {
            "normal": MEAN_NORMAL_FLOOR,
            "meat": MEAN_MEAT_FLOOR,
            "meat_target": MEAN_MEAT_TARGET,
        },
        "desktop_final_allowed": ok,
        "note": "仅 ok=true 才覆盖桌面 film_final.mp4",
    }


def write_motion_gate_receipts(
    root: Path | str,
    audit: dict[str, Any],
    gate: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Write audit (+ optional final gate) under film root receipts/."""
    base = Path(root).expanduser().resolve()
    rec = base / "receipts"
    rec.mkdir(parents=True, exist_ok=True)
    audit_path = rec / "i2v-high-motion-audit.json"
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    out: dict[str, str] = {"audit": str(audit_path)}
    if gate is not None:
        gate_path = rec / "i2v-final-gate.json"
        gate_path.write_text(
            json.dumps(gate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        out["gate"] = str(gate_path)
    return out


def still_source_allows_full_cast(wardrobe_state: str | None) -> bool:
    """Peak/undress stills must NOT sole-ref full cast master (卸装不回穿 still 源)."""
    st = str(wardrobe_state or "").strip().lower()
    if st in {"partial", "undressed", "bare"}:
        return False
    return True


def lint_still_source_policy(
    shots: list[dict[str, Any]],
) -> dict[str, Any]:
    """Hard-flag when undressed/bare shot lists sole ref as full cast master."""
    codes: list[str] = []
    issues: list[dict[str, Any]] = []
    bad: list[str] = []
    for sh in shots:
        if not isinstance(sh, dict):
            continue
        sid = str(sh.get("id") or "?")
        st = (
            str(sh.get("wardrobe_state") or (sh.get("dsl") or {}).get("wardrobe_state") or "")
            .strip()
            .lower()
        )
        if still_source_allows_full_cast(st):
            continue
        sole = (
            str(sh.get("still_source") or sh.get("keyframe_source") or sh.get("ref_kind") or "")
            .strip()
            .lower()
        )
        tags = sh.get("still_tags") or sh.get("ref_tags") or []
        blob = sole + " " + " ".join(str(t).lower() for t in tags if t)
        if any(
            m in blob
            for m in (
                "full_cast",
                "full-cast",
                "cast_master",
                "cast-master",
                "cast master",
                "full wardrobe cast",
            )
        ) and not any(
            m in blob
            for m in (
                "undress-anchor",
                "undress_anchor",
                "prior undressed",
                "state_photo",
                "state-photo",
                "already undressed",
            )
        ):
            bad.append(f"{sid}:{st}+{sole or 'cast'}")
    if bad:
        codes.append("STILL_SOURCE_FULL_CAST_RE_DRESS")
        issues.append(
            {
                "code": "STILL_SOURCE_FULL_CAST_RE_DRESS",
                "severity": "error",
                "message": (
                    "peak/undressed still sole-ref is full cast master (回穿风险) — "
                    + ", ".join(bad[:8])
                    + "。用 undress-anchor 或 prior undressed still，禁 image_edit(全装 cast)"
                ),
            }
        )
    return {
        "ok": len(codes) == 0,
        "codes": codes,
        "issues": issues,
        "bad_shots": bad,
        "note": "wardrobe partial|undressed|bare → still source ≠ full cast master",
    }

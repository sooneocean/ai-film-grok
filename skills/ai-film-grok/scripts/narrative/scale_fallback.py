"""Scale fallback ladder · 卸装不回穿 + 全裸诱惑 + 模型极限勿硬上 (2026-08-06).

Order of adjudication when generation fails:
  1) no re-dress (handled by heat wardrobe clamp)
  2) true bare / penetration when stable
  3) bare tease MAX if penetration blocked
  4) model-limit soft-max (implied-bare / undressed extreme) — stop hard-on

Does not soften heat floors; only classifies honesty + stop signals.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

# Achieved delivery tiers (not heat_phase names). Higher = more exposed.
WARDROBE_TIER_RANK: dict[str, int] = {
    "full": 0,
    "dressed": 0,
    "partial": 1,
    "undressed": 2,
    "implied-bare": 3,
    "implied_bare": 3,
    "soft-max": 4,
    "soft_max": 4,
    "bare": 5,
}

# Aliases from film-spec / dsl
_TIER_ALIASES: dict[str, str] = {
    "clothed": "full",
    "dressed": "full",
    "full": "full",
    "partial": "partial",
    "half": "partial",
    "lingerie": "partial",
    "underwear": "partial",
    "undressed": "undressed",
    "nude-ish": "implied-bare",
    "implied": "implied-bare",
    "implied-bare": "implied-bare",
    "implied_bare": "implied-bare",
    "soft-max": "soft-max",
    "soft_max": "soft-max",
    "model-limit": "soft-max",
    "model_limit": "soft-max",
    "bare": "bare",
    "nude": "bare",
    "naked": "bare",
}


def normalize_wardrobe_tier(raw: object) -> str | None:
    if raw is None:
        return None
    s = str(raw).strip().lower().replace(" ", "-")
    if not s:
        return None
    if s in _TIER_ALIASES:
        return _TIER_ALIASES[s]
    if s in WARDROBE_TIER_RANK:
        return "full" if s == "dressed" else s
    # fuzzy
    if "bare" in s or "nude" in s or "naked" in s:
        if "implied" in s or "soft" in s:
            return "implied-bare"
        return "bare"
    if "undress" in s:
        return "undressed"
    if "partial" in s or "lingerie" in s:
        return "partial"
    if "full" in s or "dress" in s or "clothed" in s:
        return "full"
    return None


def tier_rank(tier: str | None) -> int:
    if not tier:
        return -1
    t = normalize_wardrobe_tier(tier) or tier
    return int(WARDROBE_TIER_RANK.get(t, -1))


def peak_achieved_wardrobe(shots: list[dict[str, Any]] | None) -> dict[str, Any]:
    """Max wardrobe tier across shots (spec/dsl)."""
    peak: str | None = None
    peak_sid: str | None = None
    rows: list[dict[str, Any]] = []
    for sh in shots or []:
        if not isinstance(sh, dict):
            continue
        sid = str(sh.get("id") or "")
        dsl = sh.get("dsl") if isinstance(sh.get("dsl"), dict) else {}
        raw = sh.get("wardrobe_state") or dsl.get("wardrobe_state")
        tier = normalize_wardrobe_tier(raw)
        rows.append({"id": sid, "tier": tier, "raw": raw})
        if tier is not None and tier_rank(tier) > tier_rank(peak):
            peak = tier
            peak_sid = sid
    return {
        "peak_tier": peak,
        "peak_shot_id": peak_sid,
        "peak_rank": tier_rank(peak),
        "shots": rows,
    }


def demote_tier(tier: str | None) -> str:
    """One step down the scale ladder (for hard-on stop)."""
    t = normalize_wardrobe_tier(tier) or "bare"
    order = ["full", "partial", "undressed", "implied-bare", "soft-max", "bare"]
    if t not in order:
        return "soft-max"
    i = order.index(t)
    return order[max(0, i - 1)]


class ScalePromoteBanError(ValueError):
    """Blind promote blocked while scale-fallback promote_ban is active."""


def scale_promote_skip() -> bool:
    import os

    return os.environ.get("AIFILM_SKIP_SCALE_PROMOTE_GATE", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def load_scale_fallback_receipt(root: Path | str) -> dict[str, Any] | None:
    from util import read_json

    path = Path(root).expanduser().resolve() / "receipts" / "scale-fallback.json"
    data = read_json(path) if path.is_file() else None
    return data if isinstance(data, dict) else None


def promote_ban_active(receipt: dict[str, Any] | None) -> tuple[bool, list[str]]:
    """True if root or nested decision has promote_ban."""
    if not isinstance(receipt, dict):
        return False, []
    ban = bool(receipt.get("promote_ban"))
    codes = list(receipt.get("codes") or [])
    dec = receipt.get("decision") if isinstance(receipt.get("decision"), dict) else {}
    if dec.get("promote_ban"):
        ban = True
        codes = list(dec.get("codes") or codes)
    return ban, [str(c) for c in codes]


def review_note_accepts_scale_fallback(review_note: str | None) -> bool:
    note_l = str(review_note or "").lower()
    return any(
        tok in note_l
        for tok in (
            "soft-max",
            "soft_max",
            "model-limit",
            "scale_fallback",
            "scale-fallback",
            "fallback accepted",
        )
    )


def assert_scale_promote_allowed(
    root: Path | str,
    *,
    review_note: str | None = None,
    kind: str = "clip",
) -> dict[str, Any]:
    """I1.5 · fail-closed promote/register when scale-fallback promote_ban is set.

    Escape: ``AIFILM_SKIP_SCALE_PROMOTE_GATE=1`` or review-note tokens (soft-max/…).
    """
    if scale_promote_skip():
        return {
            "ok": True,
            "skipped": True,
            "escape": "AIFILM_SKIP_SCALE_PROMOTE_GATE=1",
            "kind": kind,
        }
    sf = load_scale_fallback_receipt(root)
    ban, codes = promote_ban_active(sf)
    if not ban:
        return {"ok": True, "promote_ban": False, "kind": kind, "codes": codes}
    if review_note_accepts_scale_fallback(review_note):
        return {
            "ok": True,
            "promote_ban": True,
            "human_accepted": True,
            "kind": kind,
            "codes": codes,
        }
    raise ScalePromoteBanError(
        f"scale_fallback promote_ban active for {kind} "
        f"(codes={codes}) — do not blind-approve collapsed bare; "
        "re-gen at recommended_tier / soft-max, or pass review-note containing "
        "'soft-max' / 'scale_fallback' after human accept. "
        "Escape: AIFILM_SKIP_SCALE_PROMOTE_GATE=1"
    )


def decide_scale_fallback(
    *,
    target_tier: str = "bare",
    achieved_tier: str | None = None,
    consecutive_poison: int = 0,
    consecutive_moderation: int = 0,
    consecutive_anatomy_fail: int = 0,
    hard_on_threshold: int = 2,
    penetration_failed: bool = False,
) -> dict[str, Any]:
    """Return action + codes. Fail-closed stop on poison/anatomy streaks."""
    target = normalize_wardrobe_tier(target_tier) or "bare"
    achieved = normalize_wardrobe_tier(achieved_tier)
    thr = max(1, int(hard_on_threshold))
    poison_n = int(consecutive_poison or 0)
    mod_n = int(consecutive_moderation or 0)
    anat_n = int(consecutive_anatomy_fail or 0)
    codes: list[str] = []
    honest: list[str] = []

    # P0 · 模型极限勿硬上
    if poison_n >= thr or anat_n >= thr:
        next_t = demote_tier(target)
        if next_t == "bare":
            next_t = "soft-max"
        codes.append("SCALE_HARD_ON_BAN")
        honest.append(
            f"stop hard-on after poison={poison_n}/anatomy_fail={anat_n} "
            f"(threshold {thr}); switch to model-limit stable frame"
        )
        return {
            "ok": False,
            "action": "stop_hard_on",
            "codes": codes,
            "target_tier": target,
            "achieved_tier": achieved,
            "recommended_tier": next_t,
            "partial": True,
            "honest_limits": honest,
            "promote_ban": True,
            "note": "崩坏/毒镜连出 → 勿再加 bare 词硬刷；换 soft-max/implied-bare 可画方案",
        }

    if penetration_failed or (mod_n >= thr and tier_rank(target) >= tier_rank("bare")):
        codes.append("SCALE_BARE_TEASE_FALLBACK")
        honest.append("penetration/bare blocked → bare tease MAX, not clothed fake meat")
        return {
            "ok": True,
            "action": "bare_tease",
            "codes": codes,
            "target_tier": target,
            "achieved_tier": achieved,
            "recommended_tier": "bare",
            "partial": True,
            "honest_limits": honest,
            "promote_ban": False,
            "note": "真办事做不到 → 全裸诱惑 MAX（禁内裤/半脱装绿）",
        }

    if achieved and tier_rank(achieved) < tier_rank(target):
        if tier_rank(achieved) >= tier_rank("soft-max") or tier_rank(achieved) >= tier_rank(
            "implied-bare"
        ):
            codes.append("SCALE_SOFT_MAX")
            honest.append(
                f"achieved {achieved} < target {target}; delivery PARTIAL at model-stable tier"
            )
            return {
                "ok": True,
                "action": "accept_soft_max",
                "codes": codes,
                "target_tier": target,
                "achieved_tier": achieved,
                "recommended_tier": achieved,
                "partial": True,
                "honest_limits": honest,
                "promote_ban": False,
                "note": "以模型能稳出的最高色气交付，勿硬冲 target",
            }
        if tier_rank(achieved) >= tier_rank("undressed"):
            codes.append("SCALE_WARDROBE_PARTIAL")
            honest.append(f"achieved undressed-level {achieved}; target {target} not met")
            return {
                "ok": True,
                "action": "partial_undressed",
                "codes": codes,
                "target_tier": target,
                "achieved_tier": achieved,
                "recommended_tier": "soft-max",
                "partial": True,
                "honest_limits": honest,
                "promote_ban": False,
                "note": "已脱档 PARTIAL；下一目标 soft-max/bare tease，禁回穿",
            }

    return {
        "ok": True,
        "action": "hold",
        "codes": [],
        "target_tier": target,
        "achieved_tier": achieved,
        "recommended_tier": target,
        "partial": False,
        "honest_limits": [],
        "promote_ban": False,
        "note": "on target or no gap",
    }


def report_scale_fallback_for_shots(
    shots: list[dict[str, Any]] | None,
    *,
    heat_scale: str = "max",
    consecutive_poison: int = 0,
    consecutive_moderation: int = 0,
    consecutive_anatomy_fail: int = 0,
    penetration_failed: bool = False,
) -> dict[str, Any]:
    """Compose peak wardrobe + fallback decision for delivery honesty."""
    peak = peak_achieved_wardrobe(shots)
    target = "bare" if str(heat_scale or "").lower() in {"max", "hot"} else "undressed"
    decision = decide_scale_fallback(
        target_tier=target,
        achieved_tier=peak.get("peak_tier"),
        consecutive_poison=consecutive_poison,
        consecutive_moderation=consecutive_moderation,
        consecutive_anatomy_fail=consecutive_anatomy_fail,
        penetration_failed=penetration_failed,
    )
    # S3 · ambition vs honest cap (model-limit delivery)
    ambition = target
    honest_cap = (
        decision.get("recommended_tier")
        or peak.get("peak_tier")
        or ("soft-max" if decision.get("partial") else target)
    )
    return {
        "kind": "scale-fallback",
        "schema_version": 1,
        "heat_scale": heat_scale,
        "peak": peak,
        "decision": decision,
        "codes": list(decision.get("codes") or []),
        "partial": bool(decision.get("partial")),
        "honest_limits": list(decision.get("honest_limits") or []),
        "achieved_wardrobe_tier": peak.get("peak_tier"),
        "recommended_tier": decision.get("recommended_tier"),
        "promote_ban": bool(decision.get("promote_ban")),
        "wardrobe_ambition": ambition,
        "wardrobe_honest_cap": honest_cap,
        "ambition_met": tier_rank(peak.get("peak_tier")) >= tier_rank(ambition),
    }


def write_scale_fallback_receipt(root: Path | str, payload: dict[str, Any]) -> Path:
    root_p = Path(root).expanduser().resolve()
    out = root_p / "receipts" / "scale-fallback.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        from util import write_json

        write_json(out, payload)
    except ImportError:  # pragma: no cover
        import json

        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return out


def flatten_spec_shots(spec: dict[str, Any] | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not isinstance(spec, dict):
        return out
    for sc in spec.get("scenes") or []:
        if not isinstance(sc, dict):
            continue
        for sh in sc.get("shots") or []:
            if isinstance(sh, dict):
                out.append(sh)
    if not out:
        for sh in spec.get("shots") or []:
            if isinstance(sh, dict):
                out.append(sh)
    return out

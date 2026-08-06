"""Heat phase normalize / escalate (M4 pack peel · 2026-08-06).

Cycle-free leaf — do not import edit_policy or edit_policy_heat at load.
Public symbols re-exported by narrative.edit_policy_heat / edit_policy.
"""

from __future__ import annotations

from typing import Any

from edit_policy_shared import PolicyError

__all__ = [
    "HEAT_SCALES",
    "HEAT_PHASES",
    "INTIMACY_PHASES",
    "SEX_PHASES",
    "ADVISORY_MAX_INTIMACY_RATIO",
    "ADVISORY_MAX_SETUP_RATIO",
    "ADVISORY_MAX_SEX_DURATION_RATIO",
    "EXTREME_INTIMACY_FLOOR",
    "EXTREME_SETUP_CEILING",
    "DEFAULT_SEX_DURATION_FLOOR",
    "HOT_SEX_DURATION_FLOOR",
    "HARDCORE_SEX_DURATION_TARGET",
    "DEFAULT_BARE_PEAK_REQUIRED",
    "HEAT_PHASE_ESCALATION_RANK",
    "MAX_PRE_CLIMAX_PLATEAU_SHOTS",
    "DEFAULT_SHOT_DURATION_SEC",
    "_DRAMATIC_TO_HEAT_PHASE",
    "normalize_heat_scale",
    "normalize_heat_phase",
    "infer_heat_phase",
    "apply_heat_phase_defaults",
    "heat_phase_escalation_rank",
    "lint_heat_escalation_challenge",
]


# --- phase / scale IRON constants (moved with pack) ---
HEAT_SCALES = frozenset({"soft", "medium", "hot", "max"})
HEAT_PHASES = frozenset({"setup", "foreplay", "act", "climax", "afterglow", "bridge"})
INTIMACY_PHASES = frozenset({"foreplay", "act", "climax"})
SEX_PHASES = frozenset({"act", "climax"})
ADVISORY_MAX_INTIMACY_RATIO = 0.70
ADVISORY_MAX_SETUP_RATIO = 0.20
ADVISORY_MAX_SEX_DURATION_RATIO = 0.55
EXTREME_INTIMACY_FLOOR = 0.60
EXTREME_SETUP_CEILING = 0.20
DEFAULT_SEX_DURATION_FLOOR = 0.50
HOT_SEX_DURATION_FLOOR = 0.15
HARDCORE_SEX_DURATION_TARGET = 0.55
DEFAULT_BARE_PEAK_REQUIRED = True
HEAT_PHASE_ESCALATION_RANK: dict[str, int] = {
    "setup": 0,
    "bridge": 0,
    "foreplay": 1,
    "act": 2,
    "climax": 3,
    "afterglow": 4,
}
MAX_PRE_CLIMAX_PLATEAU_SHOTS = 2
DEFAULT_SHOT_DURATION_SEC = 6.0

_DRAMATIC_TO_HEAT_PHASE: dict[str, str] = {
    "hook": "setup",
    "approach": "setup",
    "bridge": "bridge",
    "sensory": "foreplay",
    "reaction": "foreplay",
    "action": "act",
    "afterglow": "afterglow",
}

def normalize_heat_scale(value: object | None, *, default: str | None = None) -> str | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return default
    s = str(value).strip().lower()
    if s not in HEAT_SCALES:
        raise PolicyError(f"heat_scale must be one of {sorted(HEAT_SCALES)}; got {value!r}")
    return s


def normalize_heat_phase(value: object | None) -> str | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    s = str(value).strip().lower()
    if s not in HEAT_PHASES:
        raise PolicyError(f"heat_phase must be one of {sorted(HEAT_PHASES)}; got {value!r}")
    return s


def infer_heat_phase(shot: dict[str, Any]) -> str:
    """Infer heat_phase from explicit field or dramatic_function."""
    explicit = normalize_heat_phase(shot.get("heat_phase"))
    if explicit:
        return explicit
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    explicit = normalize_heat_phase(dsl.get("heat_phase"))
    if explicit:
        return explicit
    df = str(shot.get("dramatic_function") or "").strip().lower()
    # max-scale action near end often climax: leave to author; default act
    return _DRAMATIC_TO_HEAT_PHASE.get(df, "bridge")


def apply_heat_phase_defaults(shots: list[dict[str, Any]]) -> list[str]:
    """Optionally fill missing heat_phase from dramatic_function only (no climax guessing)."""
    filled: list[str] = []
    for i, shot in enumerate(shots):
        if not isinstance(shot, dict):
            continue
        if normalize_heat_phase(shot.get("heat_phase")):
            continue
        phase = infer_heat_phase(shot)
        shot["heat_phase"] = phase
        filled.append(str(shot.get("id") or f"idx{i}"))
    return filled


def heat_phase_escalation_rank(phase: str | None) -> int:
    """Higher = hotter. afterglow only valid after climax peak."""
    if not phase:
        return 0
    return HEAT_PHASE_ESCALATION_RANK.get(str(phase).strip().lower(), 0)


def lint_heat_escalation_challenge(
    shots: list[dict[str, Any]],
    *,
    heat_scale: str | None = None,
) -> dict[str, Any]:
    """Force continuous challenge of maximum heat on max films.

    Product rule (2026-07-24 user): 持续挑战尺度最大.
    - Phase rank must not drop before climax (泄火 = fail)
    - After first act, cannot return to setup for body-avoidance
    - Pre-climax: cannot plateau same rank for > MAX_PRE_CLIMAX_PLATEAU_SHOTS
      without advancing (stall = fail)
    - Afterglow only after climax peak was reached
    """
    scale = (heat_scale or "").strip().lower() or None
    issues: list[dict[str, Any]] = []
    codes: list[str] = []

    def _issue(code: str, severity: str, message: str) -> None:
        codes.append(code)
        issues.append({"code": code, "severity": severity, "message": message})

    if scale not in {"max", "hot"}:
        return {
            "ok": True,
            "codes": [],
            "warning_count": 0,
            "info_count": 0,
            "issues": [],
            "heat_scale": scale,
            "note": "escalation challenge skipped (not max/hot)",
        }

    peak_rank = -1
    peak_sid: str | None = None
    climax_seen = False
    plateau_run = 0
    last_rank: int | None = None
    regression_ids: list[str] = []
    stall_ids: list[str] = []
    afterglow_early: list[str] = []
    post_act_setup: list[str] = []
    act_seen = False
    per_shot: list[dict[str, Any]] = []

    for shot in shots:
        if not isinstance(shot, dict):
            continue
        sid = str(shot.get("id") or "?")
        ph = infer_heat_phase(shot)
        rank = heat_phase_escalation_rank(ph)
        row: dict[str, Any] = {"id": sid, "heat_phase": ph, "rank": rank}

        if ph == "climax":
            climax_seen = True
        if ph == "act":
            act_seen = True

        # afterglow before any climax = premature cool-down
        if ph == "afterglow" and not climax_seen:
            afterglow_early.append(sid)
            row["early_afterglow"] = True

        # phase regression before climax (泄火)
        if not climax_seen and peak_rank >= 0 and rank < peak_rank:
            # allow bridge as connective tissue only if rank gap is small and not from act
            if not (ph == "bridge" and peak_rank <= 1):
                regression_ids.append(f"{sid}:{ph}<peak@{peak_sid or '?'}")
                row["regression"] = True

        # after act has started, setup = body avoidance (泄火铺垫)
        if act_seen and not climax_seen and ph == "setup":
            post_act_setup.append(sid)
            row["post_act_setup"] = True

        # plateau: only pre-act ranks (setup/foreplay) — act may run long for meat %
        # stall = stuck in foreplay/setup without ascending to act/climax
        if not climax_seen and 0 < rank < 2:  # foreplay only
            if last_rank is not None and rank == last_rank:
                plateau_run += 1
            else:
                plateau_run = 1
            if plateau_run > MAX_PRE_CLIMAX_PLATEAU_SHOTS:
                stall_ids.append(sid)
                row["stall"] = True
        elif not climax_seen and rank == 0 and last_rank == 0:
            # long pure setup also stalls challenge
            plateau_run = (plateau_run + 1) if last_rank == 0 else 1
            # setup may open film: allow more (3) before stall
            if plateau_run > MAX_PRE_CLIMAX_PLATEAU_SHOTS + 1:
                stall_ids.append(sid)
                row["stall"] = True
        else:
            if rank >= 2:
                plateau_run = 0
            elif last_rank != rank:
                plateau_run = 1

        if rank > peak_rank:
            peak_rank = rank
            peak_sid = sid
        last_rank = rank
        per_shot.append(row)

    if regression_ids:
        _issue(
            "HEAT_ESCALATION_REGRESSION",
            "warning",
            "max IRON continuous challenge: heat_phase regressed before climax (泄火) — "
            f"{', '.join(regression_ids[:8])}. "
            "Phase must only rise setup→foreplay→act→climax until peak. "
            "禁止中途回到更冷的 phase。",
        )
    if post_act_setup:
        _issue(
            "HEAT_ESCALATION_REGRESSION",
            "warning",
            "max IRON: setup after act started (回避身体) — "
            f"{', '.join(post_act_setup[:8])}. 进入 act 后禁止再写 setup 泄火。",
        )
    if afterglow_early:
        _issue(
            "HEAT_ESCALATION_REGRESSION",
            "warning",
            "max IRON: afterglow before climax — "
            f"{', '.join(afterglow_early[:8])}. 高潮前禁止 afterglow 收火。",
        )
    if stall_ids:
        _issue(
            "HEAT_ESCALATION_STALL",
            "warning",
            "max IRON continuous challenge: pre-climax phase plateau too long — "
            f"{', '.join(stall_ids[:8])}. "
            f"同一 heat 档位连续 >{MAX_PRE_CLIMAX_PLATEAU_SHOTS} 镜必须加压升档 "
            "(foreplay→act 或 act→climax / 换体位加深)。持续挑战尺度最大。",
        )
    # No climax on max with enough shots = never reached maximum challenge
    n = sum(1 for s in shots if isinstance(s, dict))
    if scale == "max" and n >= 6 and not climax_seen and act_seen:
        _issue(
            "HEAT_ESCALATION_NO_PEAK",
            "warning",
            "max IRON: act without climax — 持续挑战必须抵达 climax bare 峰值，禁止只办事不办穿。",
        )

    warn_n = sum(1 for i in issues if i.get("severity") == "warning")
    return {
        "ok": warn_n == 0,
        "codes": sorted(set(codes)),
        "warning_count": warn_n,
        "info_count": 0,
        "issues": issues,
        "heat_scale": scale,
        "peak_rank": peak_rank,
        "climax_seen": climax_seen,
        "regression_shots": regression_ids,
        "stall_shots": stall_ids,
        "per_shot": per_shot,
        "note": (
            "Continuous challenge max scale: phase monotonic rise to climax; "
            "no mid-film cool-down; no long plateau. See adult-max-iron."
        ),
    }

